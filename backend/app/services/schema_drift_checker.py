import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class SchemaDriftChecker:
    """Monitors Unicommerce CSV export headers and data integrity for unexpected changes."""

    KNOWN_SALES_HEADERS = {
        "Sale Order Number", "Sale Order Item Code", "Display Order Code",
        "Channel Name", "Product SKU Code", "Product Name", "Quantity",
        "Selling Price", "Discount", "Tax", "Refund", "Category", "Status",
        "Order Date", "Dispatch Date", "Delivery Date", "Cancel Date",
        "Return Date", "Warehouse", "Customer Name", "Shipping Address City"
    }

    KNOWN_RETURN_HEADERS = {
        "Date", "Sale Order Number", "Product SKU Code", "Return Reason",
        "Quantity", "Refund Amount", "Total", "Sales", "Return Type",
        "rpcode", "RP Code", "Invoice number", "Channel entry", "Product Name",
        "Unit Price"
    }

    @classmethod
    def check_drift(cls, entity_type: str, headers: List[str]) -> bool:
        """Returns True if no drift is detected, False otherwise."""
        if not headers:
            return True
            
        header_set = set(headers)
        if entity_type == "sales_order":
            expected = cls.KNOWN_SALES_HEADERS
        elif entity_type == "return_gst":
            expected = cls.KNOWN_RETURN_HEADERS
        else:
            return True
            
        # Check if we are missing any critical headers
        # We allow new headers to appear, but we shouldn't lose core ones.
        missing = [h for h in expected if h not in header_set and h.lower() not in [x.lower() for x in header_set]]
        
        # Some headers might have alternative names, but this is a strict warning check.
        # Unicommerce changes "Refund Amount" to "Total" sometimes.
        
        if missing:
            logger.warning(f"Schema Drift Detected for {entity_type}: Missing expected headers: {missing}")
            # We don't fail immediately because Unicommerce might have renamed columns 
            # and our parsers use multiple fallbacks, but we mark it as drifted.
            return False
            
        return True

    @classmethod
    def validate_integrity(cls, entity_type: str, raw_row: Dict[str, Any]) -> List[str]:
        """Validates business rules for a single row."""
        errors = []
        try:
            if entity_type == "return_gst":
                qty = float(raw_row.get("Quantity", 0) or 0)
                refund = float(raw_row.get("Refund Amount", raw_row.get("Total", raw_row.get("Sales", 0))) or 0)
                sales = float(raw_row.get("Sales", 0) or 0)
                
                if refund < 0 or sales < 0:
                    errors.append(f"Negative revenue detected: refund={refund}, sales={sales}")
                
                if sales > 0 and refund > sales * 1.5:  # Allow some leniency for tax/shipping differences
                    errors.append(f"Refund ({refund}) significantly exceeds sales ({sales})")
                    
            elif entity_type == "sales_order":
                price = float(raw_row.get("Selling Price", 0) or 0)
                if price < 0:
                    errors.append(f"Negative selling price detected: {price}")
        except ValueError:
            pass # Data type mismatch handled by parser
            
        return errors
