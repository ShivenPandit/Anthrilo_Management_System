"""
Get RAW Unicommerce data for a known ₹0 SHOPIFY order.
Run from backend/
"""
import httpx
from datetime import datetime, timezone
from app.services.unicommerce_optimized import get_unicommerce_service
import asyncio
import sys
sys.path.insert(0, '.')

TARGET_SKUS = {"AN68274", "AN46835", "AN46868"}


async def main():
    svc = get_unicommerce_service()

    # Find an order with the target SKU
    print("Fetching Feb 3-4 to find a target order code...")
    from_dt = datetime(2026, 2, 3, 0, 0, 0, tzinfo=timezone.utc)
    to_dt = datetime(2026, 2, 4, 23, 59, 59, tzinfo=timezone.utc)
    result = await svc.fetch_all_orders_with_revenue(from_dt, to_dt)
    orders = result.get("orders", [])
    print(f"Got {len(orders)} processed orders")

    target_codes = []
    for order in orders:
        for item in order.get("saleOrderItems", []):
            if item.get("itemSku") in TARGET_SKUS:
                target_codes.append(order.get("code"))
                break

    if not target_codes:
        print("No target SKUs in Feb 3-4. Trying Feb 7-9...")
        from_dt = datetime(2026, 2, 7, 0, 0, 0, tzinfo=timezone.utc)
        to_dt = datetime(2026, 2, 9, 23, 59, 59, tzinfo=timezone.utc)
        result = await svc.fetch_all_orders_with_revenue(from_dt, to_dt)
        orders = result.get("orders", [])
        for order in orders:
            for item in order.get("saleOrderItems", []):
                if item.get("itemSku") in TARGET_SKUS:
                    target_codes.append(order.get("code"))
                    if len(target_codes) >= 3:
                        break
            if len(target_codes) >= 3:
                break

    print(
        f"\nFound {len(target_codes)} target order codes: {target_codes[:5]}")

    if not target_codes:
        print("No target orders found. SKUs not in this date range.")
        return

    # Now fetch RAW (bypassing extraction) for the first 2 codes
    headers = await svc._get_headers()
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), limits=svc.limits) as client:
        for code in target_codes[:2]:
            r = await client.post(
                f"{svc.base_url}/oms/saleorder/get",
                json={"code": code, "paymentDetailRequired": True},
                headers=headers,
            )
            data = r.json()
            if not data.get("successful"):
                print(f"Failed to get {code}")
                continue
            raw = data.get("saleOrderDTO", {})
            print(f"\n{'='*70}")
            print(
                f"ORDER: {code}  channel={raw.get('channel')}  status={raw.get('status')}")

            # Order-level ALL fields (except items and packages)
            print("\nALL ORDER-LEVEL FIELDS (non-list):")
            for k, v in sorted(raw.items()):
                if k not in ('saleOrderItems', 'shippingPackages', 'paymentDetails', 'customFieldValues'):
                    print(f"  {k}: {repr(v)}")

            # First package
            for pkg in raw.get("shippingPackages", [])[:1]:
                print("\nSHIPPING PACKAGE:")
                for k, v in sorted(pkg.items()):
                    if k not in ('shippingPackageItems',):
                        print(f"  {k}: {repr(v)}")

            # Items
            print(f"\nITEMS ({len(raw.get('saleOrderItems', []))} total):")
            for itm in raw.get("saleOrderItems", [])[:3]:
                print(
                    f"  SKU={itm.get('itemSku')} name={itm.get('itemName')[:40] if itm.get('itemName') else '?'}")
                for k, v in sorted(itm.items()):
                    if any(x in k.lower() for x in ('price', 'amount', 'discount', 'rate', 'gst', 'tax', 'mrp', 'value', 'channel')):
                        print(f"    {k}: {repr(v)}")

            # Payment details
            for pd in raw.get("paymentDetails", [])[:2]:
                print(f"\nPAYMENT DETAIL: {pd}")


asyncio.run(main())
