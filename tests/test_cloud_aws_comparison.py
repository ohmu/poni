from poni import cloud

def test_hash():
    """validate aws provider hash and comparison implementation"""
    sky = cloud.Sky()
    east_prop = dict(provider="aws-ec2", region="us-east-1")
    east1 = sky.get_provider(east_prop)
    east2 = sky.get_provider(east_prop)
    assert hash(east1) == hash(east2)
    assert hash(east1) != hash(east1.get_provider_key(east_prop))
    assert east1 == east2
    assert not east1 != east2

    west = sky.get_provider(dict(provider="aws-ec2", region="us-west-1"))
    assert hash(east1) != hash(west)
    assert not east1 == west
    assert east1 != west

