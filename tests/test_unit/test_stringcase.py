from utils.stringcase import camelcase, snakecase


def test_camelcase():
    assert camelcase("user_name") == "userName"
    assert camelcase("zone_type") == "zoneType"
    assert camelcase("alreadyCamel") == "alreadyCamel"


def test_snakecase():
    assert snakecase("userName") == "user_name"
    assert snakecase("ZoneType") == "zone_type"
    assert snakecase("already_snake") == "already_snake"
