def bytes_to_gb(value, digits=2):
    if value is None:
        return None
    gb = round(value / (1024 ** 3), digits)

    if digits == 0:
        return int(gb)

    return gb

def bytes_to_mb(value, digits=0):
    if value is None:
        return None

    mb = round(value / (1024 ** 2), digits)

    if digits == 0:
        return int(mb)

    return mb