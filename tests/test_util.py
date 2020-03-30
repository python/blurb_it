from blurb_it import util
from aiohttp.test_utils import make_mocked_request
from aiohttp_session import (Session, SESSION_KEY)


async def test_nonceify():
    body = "Lorem ipsum dolor amet flannel squid normcore tbh raclette enim" "pabst tumblr wolf farm-to-table bitters. Bitters keffiyeh next" "level proident normcore, et all of +1 90's in blue bottle" "chillwave lorem. Id keffiyeh microdosing cupidatat pour-over" "paleo farm-to-table tumeric sriracha +1. Raclette in poutine," "bushwick kitsch id pariatur hexagon. Thundercats shaman beard," "nulla swag echo park organic microdosing. Hot chicken tbh pop-up" "tacos, asymmetrical tilde veniam bespoke reprehenderit ut do."

    nonce = await util.nonceify(body)
    assert nonce == "Ps4kgC"


async def test_get_misc_news_filename():
    path = await util.get_misc_news_filename(
        bpo=123,
        section="Library",
        body="Lorem ipsum dolor amet flannel squid normcore tbh raclette enim"
        "pabst tumblr wolf farm-to-table bitters. Bitters keffiyeh next"
        "level proident normcore, et all of +1 90's in blue bottle"
        "chillwave lorem. Id keffiyeh microdosing cupidatat pour-over"
        "paleo farm-to-table tumeric sriracha +1. Raclette in poutine,"
        "bushwick kitsch id pariatur hexagon. Thundercats shaman beard,"
        "nulla swag echo park organic microdosing. Hot chicken tbh pop-up"
        "tacos, asymmetrical tilde veniam bespoke reprehenderit ut do.",
    )

    assert path.startswith("Misc/NEWS.d/next/Library/")
    assert path.endswith(".bpo-123.Ps4kgC.rst")


async def test_has_session():
    request = mock_request_session()

    has_session = await util.has_session(request)
    assert has_session


async def test_session_context():
    request = mock_request_session()

    session_context = await util.get_session_context(request)
    assert session_context == {"username": "blurb", "token": "124"}


def mock_request_session():
    request = make_mocked_request("GET", "/")
    session = Session("identity", data=None, new=False)
    session["token"] = "124"
    session["username"] = "blurb"
    request[SESSION_KEY] = session

    return request
