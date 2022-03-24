import string

import pytest

from blurb_it import util, error
from aiohttp.test_utils import make_mocked_request
from aiohttp_session import Session, SESSION_KEY


class FakeGH:
    def __init__(self, *, getiter=None, getitem=None, post=None):
        self._getitem_return = getitem
        self._getiter_return = getiter
        self._post_return = post
        self.getitem_url = None
        self.getiter_url = None
        self.post_url = []
        self.post_data = []

    async def getiter(self, url, jwt=None, accept=None):
        self.getiter_url = url
        for item in self._getiter_return:
            yield item


async def test_nonceify():
    body = (
        "Lorem ipsum dolor amet flannel squid normcore tbh raclette enim"
        "pabst tumblr wolf farm-to-table bitters. Bitters keffiyeh next"
        "level proident normcore, et all of +1 90's in blue bottle"
        "chillwave lorem. Id keffiyeh microdosing cupidatat pour-over"
        "paleo farm-to-table tumeric sriracha +1. Raclette in poutine,"
        "bushwick kitsch id pariatur hexagon. Thundercats shaman beard,"
        "nulla swag echo park organic microdosing. Hot chicken tbh pop-up"
        "tacos, asymmetrical tilde veniam bespoke reprehenderit ut do."
    )

    nonce = await util.nonceify(body)
    assert nonce == "Ps4kgC"


async def test_get_misc_news_filename():
    path = await util.get_misc_news_filename(
        issue_number=123,
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
    assert path.endswith(".gh-issue-123.Ps4kgC.rst")


async def test_has_session():
    request = mock_request_session()

    has_session = await util.has_session(request)
    assert has_session


async def test_session_context():
    request = mock_request_session()

    session_context = await util.get_session_context(request)
    assert session_context == {"username": "blurb", "token": "124"}


async def test_no_session_context():
    request = mock_request_no_session()

    session_context = await util.get_session_context(request)
    assert session_context == {}


def mock_request_session():
    request = make_mocked_request("GET", "/")
    session = Session("identity", data=None, new=False)
    session["token"] = "124"
    session["username"] = "blurb"
    request[SESSION_KEY] = session

    return request


def mock_request_no_session():
    request = make_mocked_request("GET", "/")
    session = Session("identity", data=None, new=False)
    request[SESSION_KEY] = session
    return request


def test_get_csrf_token__not_existing(mocker):
    mocker.patch("blurb_it.util.create_csrf_token", return_value="foobar")

    assert util.get_csrf_token({}) == "foobar"


def test_get_csrf_token__existing():

    assert util.get_csrf_token({"csrf": "foobar"}) == "foobar"


def test_create_csrf_token():
    token = util.create_csrf_token()
    assert len(token) == 43
    assert set(token) <= set(string.ascii_letters + string.digits + "-_=")


@pytest.mark.parametrize("token, match", [("a", True), ("b", False)])
def test_compare_csrf_tokens__match(token, match):
    assert util.compare_csrf_tokens("a", token) is match


async def test_get_installation():
    app_installations = [
        {
            "id": 1,
            "account": {
                "login": "octocat",
                "id": 1,
            },
        }
    ]
    gh = FakeGH(getiter=app_installations)
    result = await util.get_installation(gh, "fake_jwt", "octocat")
    assert result == app_installations[0]


async def test_get_installation_not_found():
    app_installations = [
        {
            "id": 1,
            "account": {
                "login": "octocat",
                "id": 1,
            },
        },
        {
            "id": 1,
            "account": {
                "login": "octosaurus",
                "id": 1,
            },
        },
    ]
    gh = FakeGH(getiter=app_installations)
    with pytest.raises(error.InstallationNotFound) as exc:
        await util.get_installation(gh, "fake_jwt", "octonauts")
    assert exc.value.args[0] == "Can't find installation by that user: octonauts"
