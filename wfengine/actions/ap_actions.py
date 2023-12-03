"""Actions pertaining to the Accounts Payable Workflow."""

import logging

from typing import Any, Dict, List

from wfengine.base_runner import ActionRegister, BaseRunner, RunStatus

logger = logging.getLogger(__name__)


@ActionRegister(label="Run PDF Extraction Actions")
class ExtractPdfRunner(BaseRunner):
    """
    Run PDF Extraction Action: Use pytesseract for OCR and PDFMiner
    to extract text from the PDF.
    """

    def input_keys(self) -> Dict[str, str]:
        return {"pdf_file": "PDF File to extract text from"}

    def output_keys(self) -> List[str]:
        return ["data"]

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run the extract action."""
        document_type = kwargs.get("document_type")
        if document_type == "INVOICE":
            invoice_data = {"po_number": 123, "inv_amount": 1235.00}
            logger.info(f"Extracted Invoice: {invoice_data}")
            return {"data": invoice_data, "status": RunStatus.COMPLETED}
        elif document_type == "PO":
            po_data = {"po_number": 123, "grn_numbers": [1, 2, 3]}
            logger.info(f"Extracted PO: {po_data}")
            return {"data": po_data, "status": RunStatus.COMPLETED}
        elif document_type == "GRN":
            # Multiple GRNS can be extracted from a single GRN PDF?
            grn_data = {"grn_number": 1, "po_number": 123}
            logger.info(f"Extracted GRN: {grn_data}")
            return {"data": grn_data, "status": RunStatus.COMPLETED}

        return {
            "data": {},
            "status": RunStatus.FAILED,
            "reason": f"Unknown Document type {document_type}",
        }


@ActionRegister(label="Invoice Verification using 2-way or 3-way")
class VerifyInvoiceRunner(BaseRunner):
    """Run Invoice Verification."""

    def input_keys(self) -> Dict[str, str]:
        return {
            "invoice_data": "Invoice Data",
            "purchase_order_data": "PO Data",
            # "grn_data": "GRN Data" ## Optional
        }

    def output_keys(self) -> List[str]:
        return ["verified"]

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run the invoice verification action."""
        inv_data = kwargs.get("invoice_data")
        po_data = kwargs.get("purchase_order_data")
        if inv_data["po_number"] == po_data["po_number"]:
            logger.info(f"Invoice Verified: PO # {po_data['po_number']}")
            return {"verified": True, "status": RunStatus.COMPLETED}
        else:
            logger.info(f"Invoice Verification Failed: {kwargs}")
        return {"verified": False, "status": RunStatus.FAILED}


@ActionRegister(label="Save Data into the ERP")
class ErpRunner(BaseRunner):
    """Save Data into the ERP"""

    def input_keys(self) -> Dict[str, str]:
        return {
            "invoice_data": "Invoice Data",
        }

    def output_keys(self) -> List[str]:
        return ["saved"]

    def run(self, **kwargs) -> Dict[str, Any]:
        """Save the data into the ERP."""
        document_type = kwargs.get("document_type")
        method = kwargs.get("method")
        if document_type == "INVOICE" and method == "SAVE":
            invoice_data = kwargs.get("data")
            logger.info(f"Saved Invoice: {invoice_data}")
            return {"saved": True, "status": RunStatus.COMPLETED}
        elif document_type == "INVOICE" and method == "UPDATE_STATUS":
            invoice_data = kwargs.get("data")
            payment_status = kwargs.get("payment_status")
            logger.info(f"Updated Invoice: {payment_status} // {invoice_data}")
            return {"saved": True, "status": RunStatus.COMPLETED}
        # else:
        #     raise ValueError(f"Unknown ERP Document Type [{document_type}] : {kwargs}")

        logger.info(
            f"Unknown ERP Document Type [{document_type} / {method}] : {kwargs}"
        )
        return {
            "saved": False,
            "status": RunStatus.FAILED,
            "reason": "Unknown ERP Document Type",
        }


@ActionRegister(label="Trigger Payment Actions")
class PaymentRunner(BaseRunner):
    """Trigger Payment Actions"""

    def input_keys(self) -> Dict[str, str]:
        return {"invoice_data": "Invoice Data"}

    def output_keys(self) -> List[str]:
        return ["triggered"]

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run the extract action."""
        logger.info(f"Payment triggered Action: {kwargs}")
        return {"triggered": True, "status": RunStatus.COMPLETED}
