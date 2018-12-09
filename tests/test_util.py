from blurb_it import util


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
