import http
import pytest
import gidgethub


from blurb_it import util

class FakeGH:
    def __init__(self, *, getiter=None, getitem=None, post=None, patch=None):
        self._getitem_return = getitem
        self._getiter_return = getiter
        self._post_return = post
        self._patch_return = patch
        self.getitem_url = None
        self.getiter_url = None
        self.patch_url = self.patch_data = None
        self.post_url = self.post_data = None

    async def getitem(self, url):
        self.getitem_url = url
        to_return = self._getitem_return[self.getitem_url]
        if isinstance(to_return, Exception):
            raise to_return
        else:
            return to_return

    async def getiter(self, url):
        self.getiter_url = url
        to_iterate = self._getiter_return[url]
        for item in to_iterate:
            yield item

    async def patch(self, url, *, data):
        self.patch_url = url
        self.patch_data = data
        return self._patch_return

    async def post(self, url, *, data):
        self.post_url = url
        self.post_data = data
        if isinstance(self._post_return, Exception):
            raise self._post_return
        else:
            return self._post_return


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


async def test_is_core_dev():
    teams = [{"name": "not Python core"}]
    gh = FakeGH(getiter={"/orgs/python/teams": teams})
    with pytest.raises(ValueError):
        await util.is_core_dev(gh, "mariatta")

    teams = [{"name": "python core", "id": 42}]
    getitem = {"/teams/42/memberships/mariatta": True}
    gh = FakeGH(getiter={"/orgs/python/teams": teams}, getitem=getitem)
    assert await util.is_core_dev(gh, "mariatta")
    assert gh.getiter_url == "/orgs/python/teams"

    teams = [{"name": "python core", "id": 42}]
    getitem = {
        "/teams/42/memberships/miss-islington": gidgethub.BadRequest(
            status_code=http.HTTPStatus(404)
        )
    }
    gh = FakeGH(getiter={"/orgs/python/teams": teams}, getitem=getitem)
    assert not await util.is_core_dev(gh, "miss-islington")

    teams = [{"name": "python core", "id": 42}]
    getitem = {
        "/teams/42/memberships/miss-islington": gidgethub.BadRequest(
            status_code=http.HTTPStatus(400)
        )
    }
    gh = FakeGH(getiter={"/orgs/python/teams": teams}, getitem=getitem)
    with pytest.raises(gidgethub.BadRequest):
        await util.is_core_dev(gh, "miss-islington")