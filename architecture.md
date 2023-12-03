# Overview

This documents gives the overall architecture for the entire WF system with considerations to deployment, security, UI etc.

# System [Components]

- System Configuration

  - Default timeouts, retry policies for each agent (Workflow step) including default retry-able failures. [NOTE: The only retry-able errors that i can think of are systemic and not wf based: Network failures, DB Query failures?]. So, maybe, they dont need to be configurable!
  - Default WF templates for each of the supported processes!
  - Default input/output schema for each supported task, pdf document types.

- Customer Onboarding

  - Need to configure the ERP Access details [We will have 'plugins' for the more common ERPs/Databases].
  - Customer Information in the customer database. Customer Name will also be used to check the authenticity of the Invoice as well. May need customer name aliases in case they use different names with different suppliers???
  - Supplier informations in the supplier database. [Including Supplier email domains]
  - Sender email addresses should be defined as users on the system. Valid domains?
  - Processes enabled for the user (AP, AR, EXPENSE, etc)
    - Currently, we assume that only the 'AP' process is available.
  - Batch Processor configuration
    - Currently the only option is a MailProcessor with a specified IMAP configuration [User ID, Authentication Information]. This should be stored in something like AWS Secrets from a security perspective.
    - Rules to identify/verify the workflow process based on the mail attributes.
  - Workflow configuration for the chosen processes:
    - Customize the workflow from a system provided default. Customer can add/remove/configure steps. [Haven't thought through on the 'add' part]
    - Number of follow-ups. Maximum time before escalation.
    - Escalation rules [Amount, department, failure reason based]
    - Total time after which it is marked FAILED!
    - Approval Users to be defined in the system. Can be different for each step?

- Batch Processor (A Scheduled Cronjob)

  - The MailProcessor will run periodically and scan through the received mails. [IMAP Configuration needed for this]. We may need to manage state so that we dont process the same email multiple times. To not manage state, we can only fetch the "Unread/Unseen Emails".
  - Listens to all the email addresses defined across customers. We can scale based on the load per customer. There can be multiple processors configured each with a set of email addresses to listen
  - If we are integrating with each customer's email system, customer identification is easy.
  - In case they are forwarding it our mail server, then we will create separate email IDs for each customer.
  - Identifies Invoice emails [Screening]
    - Validate that 'sender' is defined as an user in the system [DONT KNOW IF THIS NEEDED]
    - Simple rules based on email fields Subject contains 'Invoice', Sender = 'xyz@abc.com', etc.
    - [LATER] Maybe compute a score to eliminate possibility of missing any invoices where the system is unsure???
  - Identifies Approval emails [For Manual Approval Steps]
  - In case there are dedicated email addresses for wf processing, any unidentified email will be logged with a reason [No attachment, Unknown Sender etc]
  - Generate a transaction ID.
    - This will be an UUID [At this point, we dont have an Invoice ID]
  - Identify/Extract Invoice file from the attachment.
    - Additionally, check if PO and Goods Received Note are also attached. [DONT KNOW IF THIS HAPPENS?]
    - Create a working directory for this invoice with the generated transaction ID. [This will need to be accessed across machines, so maybe AWS S3 or AWS EFS based on latency needs]
    - Save the invoice file in the working directory
  - Invokes the Orchestrator with the AP Workflow.
    - Inputs = [Working directory, Invoice filename, Mail metadata (Useful for audit purposes), Mail body -> Maybe some info here as well?]
    - Creates a transaction entry in a DB initiating the workflow with the working directory and the inputs [Status = NEW, Key = above UUID] => Do we need this??
    - Create a JSON with the transaction id, inputs and also store it in the working directory. In case the PO, GRN are also stored, include the file names for those as well in the JSON.
    - Invokes the Orchestrator by pusing the request to a message queue with the transaction ID. [and/or the above JSON?] with action = CREATE.

- Orchestrator

  - Listening to a Message Queue [or Kafka/Confluent]
  - Provided as a REST API to start invocation
    - which also posts a message to the message queue (action = CREATE)
  - Provided as a REST API to restart invocation after a manual over-ride
    - which also posts a message to the message queue (action = CONTINUE, step = <step_name>)
  - Auto discovery of agents supported by the system.
  - Since agents are `code`, live addition of agents will not be possible [Unless, we support a script functionality on the UI]
  - The detailed implementation is explained in wfengine.md

- Report/Audit
  - List of Invoices Processed (Date, Sender) and the status so that an 'admin' can follow through. Useful in case escalations are completed.
  - Ability to filter for Failed Invoices and failure reasons.
    - In case of tech error (ocr failure) etc, ticket can be auto-created??

# Tech Stack

1. FE: Angular or React. Either one is OK. Angular includes the kitchen sink so library hunting is needed less.
2. BE Rest APIs: Python with Flask/FastAPI (and nginx) or NodeJS would be the options that i would consider. Java/Springboot is also an option. THis is just a personal preference.
3. BE Scheduled Jobs: We will need periodically scheduled jobs to handle SLA/escalations. In python, we can use Celery with a redis MQ. I am sure that there are similar tools in all the toolchains recommended above. And this can be deployed as a separate container if needed.
4. BE Notification Handling: The Rest APIs will push the events to pub/sub Message Queue and a backend job will process them.
5. Database [See 'Deployment Considerations']

# Deployment Considerations

1. SaaS deployment on a cloud [AWS | GCP | Azure]
   - First criteria is checking if we get credits from the cloud providers.
   - Else, my personal preference is AWS followed by GCP. Below, i assume that it is AWS.
2. DB
   - My first preference will be Postgres as it has native FTS and PgVector. allows us to not invest extra in a specific search/indexing tools. Otherwise MariaDB/MySQL which has FTS but no vector search. We can also consider MongoDB as this is not a transaction oriented system. And MongoDB also includes FTS and vector search [But, Mongo also has a learning curve].
   - I would use AWS RDS or equivalent to reduce management headaches. if cost is an issue, we can set it up on AWS EC2.
   - We can setup redundancy and Multi-AZ setup for the DB. But this increases cost and is probably not needed in the initial days.
   - Backup to be setup. Say incremental backup every 6 hrs and a full backup every week.
3. Load Balancer
   - AWS ALB or HA Proxy [AWS ALB is preferred because it reduces management headaches.
4. Rest API Deployment
   - Use docker containers for the deployment. Can use Kubernetes or AWS Fargate clusters so that scalability can be done externally. Fargate is cheaper on AWS!
   - Can also check Serverless deployments. But i believe, the cost is a bit higher specially when there is scale.
5. Message Queue (or Pub/Sub)
   - Can use AWS SQS or similar initially.
   - Another option is to use AWS Kinesis [Kafka/Confluent] as it is better for scale.
6. Caching Needs [Redis]
   - Probably not needed in the initial days.
   - But we can store open workflow context as a KV redis DB. so that access time is reduced.
7. Search, Indexing: Can leverage DB provided capabilities. In the case of MariaDB, we can setup OpenSearch to handle text search.
8. Logging:
   - Can provide mechanisms to dump event logs [access logs, app events etc] to a central location that can be explored via a Grafana/Kibana interface.
9. Alarms/Monitoring:
   - Initially use AWS Cloudwatch to configure them. Can set alarms on metrics defined in AWS [DB CPU usage, DB Connections, Free diskspace etc]
10. Storage:
    - Use S3 storage.
    - Maybe, if the WF instance is completed, the associated files can be moved to 'Glacial' storage after 'n' days. This will need to be configured on S3. [Or there can be a cron-job that does this]
11. Static media
    - Provide access via CDN. Possibly, AWS Cloudfront. Again, may not be needed initially specially if it is in a single geography.
12. Customer accessibility.
    - We can provide access to customers via a <orgname>.<our_domain> URL.
    - Later, we could potentially use their domain name itself.

# Security Considerations

- Ensure that the system is deployed in a private subnet with access only from a VPN.
- Consider setting up 'Encryption at rest' for the database.
- Setup a exhaustive 'permissions' framework as a middleware --> invoked for all URL/API access.
- URL re-writing/leaking across organizations should not be possible. As far as possible, ensure that parameters are encoded in the body and available only as POST.
- Media/file access should also go through some authentication. In case of AWS S3, generate URLs and tokens which expire after a given period of time. The S3 buckets themselves should be private!
- Use JWT authentication for the API access. with appropriate expiry for the access token (1d) and the refresh tokens (1h).
- Other basic stuff [HTTPS, Owasp recommendations for CSRF, XSS]
- Deletion of 'workflow' will be a soft-delete to ensure that existing wf instances are preserved.

# Load Considerations

Parameters: - Number of orgs: 100 - Number of users per org: 1000 - Peak hours = 10 [Assuming all load comes in the 10 hrs]

- Naive Dimensioning exercise for the REST APIs
  - Daily load per user
    - Number of WFs accessed per day per user: 8
    - Number of WFs acted per day per user: 2
    - Number of files uploaded: 1
    - Number of comments: 1
  - Total system transactions per day (across all users)
    - WF Access = 100 _ 1000 _ 8 = 800,000
    - WF Actions = 100 _ 1000 _ 2 = 200,000
    - WF Files = 100 _ 1000 _ 1 = 100,000
    - WF Comments = 100 _ 1000 _ 1 = 100,000
      Total Transactions per day: 1.2 Million
  - Total transaction per peak hour = 120,000
  - Transactions per Second (TPS) = 120,000 / 3600 = 33.33 (or 34)
- Naive Dimensioning exercise for the Notifications

  - Number of actions per user per day = 2 + 1 + 1
  - Total number of notifications to be sent = 100 _ 1000 _ 4 = 400,000
  - Total notifications per peak hour = 40,000
  - Notification processing (TPS) = 40,000 / 3600 = 11.11 (or 12)

- Based on this, we can dimension the hardware/cluster requirements.
