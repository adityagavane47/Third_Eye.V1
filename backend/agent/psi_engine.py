def mock_psi(local_blacklist, external_blacklist):
    """
    Simulates Private Set Intersection (PSI)
    Returns common malicious wallets without exposing full lists
    """

    local_set = set(local_blacklist)
    external_set = set(external_blacklist)

    intersection = list(local_set.intersection(external_set))

    return intersection