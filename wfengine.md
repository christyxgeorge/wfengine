# Workflow Engine.

Multi-step process flows. Where the originator initiates the request via an UI or is periodically scheduled. It goes through multiple configurable process automation steps/bots to achieve completion of the same.

Example: Airflow. Provides an ability to orchestrate a flow with pre-built 'operators' and custom python code to execute complex ETL/ELT pipelines

# Accounts Payable Workflow

- Triggered
  - via an UI
  - via an email sent to a dedicated 'bot' account (say ap@example.com). It could also be a generic email account in which case, we will need to screen the mails for an Invoice email. The 'sender' of this mail will be marked as the workflow originator/owner/requestor.
- Process
  - Invoice capure
    - capture details from the attached invoice PDF. This will include the PO number, Supplier Info, Customer Info and the invoice lines with the item details.
    - Handle non-PO invoice
    - [LATER] It is possible that a single Invoice can refer to multiple POs.
    - [LATER] It is also possible that a single Invoice can refer to only a portion of the Invoice?
  - Obtain PO
    - obtain the PO details from the ERP. [or can it be attached to the mail?]
  - Invoice verification
    - match the invoice with PO.
    - In case of 3-way matching, obtain the Goods received notes (GRN) from the ERP based on the PO number. [or can it be attached to the mail?]
    - In case of failure:
      - manual over-ride with timed escalation(s). The user is shown a form with the extracted details and the failure reason. And the PO is attached for the user to download.
      - user can fill in the rest of the details and move the WF to the next step. [trigger an API call to restart the workflow]
      - user can also mark it as failure and specify a reason [drop_down with 'OTHER REASON' to add a custom reason]
  - Save Invoice:
    - store the invoice details into the ERP. [with the appropriate status = FOR_APPROVAL or equivalent]
  - Invoice Approval
    - This could be different people based on the amounts/departments involved?
    - Should be mail based so that there is an audit trail.
    - Mail reply will also be processed/scanned by the MailProcessor and trigger the orchestrator.
  - Payment Authorization
    - This could be an optional step that needs to go to different people.
    - Multiple Invoice approvals can be batched into a single authorization step. Maybe, there are rules defined to achieve this.
  - Trigger the Payment
    - In case of electronic payments, actually trigger the payment [API, some other interface, library, ...]
    - Or assign the workflow to an individual who will actually make the payment via other means!

# test_wf Workflow [An absolutely contrived workflow]

The test_wf workflow is defined at `./definitions/test_wf.json`. It does the following:

- google search & return the top 2 results as texts
- count the number of words in each of the results above
- run two sql queries in parallel
- return the count of rows returned by each query and sum the total rows
- generate a random number {}
- get the 'n'th word of each of the search results above where n is the random number generated above but only of the generated number is an even number { qr1, qr2 }
- send details to an email address and wait for confirmation
- confirmation received via email... --> WF = COMPLETED / FAILED.

# Installing the `wfengine` software

- Python requirements = python >= 3.10
- Install Other packages needed

  > pip install --upgrade -r requirements.txt

- Clone the repo from github
  >

# Run the accounts_payable workflow

Run the following commands: Note that the input parameters have been hard-coded in main.py

> python main.py --verbose --workflow accounts_payable

The last line of the output should show the transaction ID
Workflow ACCOUNTS_PAYABLE / Step APPROVE_INVOICE / 466c648c-c680-4d66-b8c0-7b6b62487da4 => RunStatus.WAITING // Waiting for approval

Execute the command with -t last [will use the last transaction id from the DB]

> python main.py --verbose --workflow accounts_payable -t last

After the first, approval, it will now be waiting at the next step that requires approval.
Workflow ACCOUNTS_PAYABLE / Step AUTHORIZE_PAYMENT / 466c648c-c680-4d66-b8c0-7b6b62487da4 => RunStatus.WAITING // Waiting for approval

> python main.py --verbose --workflow accounts_payable -t last

Now the workflow will be completed
Workflow ACCOUNTS_PAYABLE / Step NOTIFY_USER / 466c648c-c680-4d66-b8c0-7b6b62487da4 => RunStatus.COMPLETED // Workflow Completed

# Run the test_wf workflow

Run the following commands:

> python main.py -w test_wf --search-term "Artificial Intelligence" --verbose \
>  --approvers=xyz@example.com,mop@example.com

The last line of the output should show the transaction ID
Workflow WF_TEST / Step RESULT / 34b46dc9-3eae-4d84-b6bb-d7f29da7e234 => RunStatus.WAITING // Waiting for approval

> python main.py -w test_wf --transaction-id last --verbose --approved-by xyz@example.com

After the first, approval, it will still be waiting!
Workflow WF_TEST / Step RESULT / 34b46dc9-3eae-4d84-b6bb-d7f29da7e234 => RunStatus.WAITING // Step [Waiting]

> python main.py -w test_wf --transaction-id last --verbose --approved-by mop@example.com

Now, you should see that the workflow has completed
Workflow WF_TEST / Step RESULT / 34b46dc9-3eae-4d84-b6bb-d7f29da7e234 => RunStatus.COMPLETED // Workflow Completed

# Final Comments

The primary focus was to show the WF invocation and executing the defined flow.

There are still a lot of things that can be done to improve this.

- Input/Output mapping can be done better.
  - The type checking is limited
  - Optional parameters are not handled nicely
- Some of the actions are half-implemented.
- The WF definitions are now in an file. Need to be moved to UI/DB.
- The DB schema is extremely primitive.
- Hot loading of new actions is not possible.
- While there exists sub-workflow support, it has not been tested.
