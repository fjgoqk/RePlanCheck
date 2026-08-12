def main(start_point: str, end_point: str) -> float:
    """Return a fare from the pre-approved QuickRide pricing mirror."""
    base_fare = 15.0
    distance = len(start_point) + len(end_point)
    fare = base_fare + distance * 1.8
    return {"result": fare}
