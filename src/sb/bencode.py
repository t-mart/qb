def deserialize(data):
    """
    Recursively deserialize bencoded data.

    Example usage:
        >>> import bencodepy
        >>> bencoded_data = b'd3:bar4:spam3:fooi42ee'
        >>> decoded = bencodepy.decode(bencoded_data)
        >>> deserialized = deserialize(decoded)
        >>> print(deserialized)
        {'bar': b'spam', 'foo': 42}

    There is no attempt at making this function suitable for round-tripping back to
    bencoded format; it is only intended for human-readable representation.
    """
    if isinstance(data, dict):
        return {
            # Recursive call for keys (decoded) and values
            deserialize(k): deserialize(v)
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [deserialize(item) for item in data]
    elif isinstance(data, bytes):
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return f"binary:{data.hex()}"
    return data


if __name__ == "__main__":
    from pathlib import Path
    import bencodepy
    import json

    fastresume_path = Path("foo.fastresume")

    with fastresume_path.open("rb") as f:
        bencoded_data = bencodepy.decode(f.read())
    deserialized_data = deserialize(bencoded_data)
    print(json.dumps(deserialized_data, indent=2))
