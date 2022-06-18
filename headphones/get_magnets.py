#! /usr/bin/env python3
# vim:fenc=utf-8
#
# Copyright © 2022 i7heaven <caifangmao8@gmail.com>
#
# Distributed under terms of the MIT license.

import json
import re
import sys
import urllib
from os.path import expanduser

import requests
from rich import box
from rich.console import Console
from rich.table import Table


class Magnet:
    def __init__(
        self, index, href, magnet_url, seeds, size, title, tpb_category
    ):

        self.index = index
        self.href = href
        self.magnet_url = magnet_url
        self.seeds = seeds
        self.size = size
        self.title = title
        self.tpb_category = tpb_category
        self.set_headphones_category(tpb_category)

    def set_headphones_category(self, tpb_category):
        if "FLAC" in tpb_category:
            self.category = "104"  # losslessOnly
        else:
            self.category = "100"  # mp3 (not lossless, no FLAC)
            # TODO: distinguish between general music (100) and mp3 (101).


# PIRATE_URL = "https://thepiratebay.org"
PIRATE_URL = "https://proxifiedpiratebay.org"
PIRATE_API_URL = "https://apibay.org"


MAGNET_FORMAT = "magnet:?xt=urn:btih:{}&dn={}"

PROXY_HOST = ""
PROXY_PORT = ""

MAIN_CAT = {"0": "???"}
SUB_CAT = {"0": "???"}

raw_main_js = None

try:
    with open(expanduser("~") + "/.pirateship/config") as f:
        for line in f.readlines():
            if not line.startswith("#") and not line.find("PROXY_HOST=") == -1:
                PROXY_HOST = line[11:].rstrip("\n")
            elif (
                not line.startswith("#") and not line.find("PROXY_PORT=") == -1
            ):
                PROXY_PORT = line[11:].rstrip("\n")
            elif (
                not line.startswith("#") and not line.find("PIRATE_URL=") == -1
            ):
                PIRATE_URL = line[11:].rstrip("\n")
            elif (
                not line.startswith("#")
                and not line.find("PIRATE_API_URL=") == -1
            ):
                PIRATE_API_URL = line[15:].rstrip("\n")
except FileNotFoundError:
    pass


def request(url, params={}):
    if len(PROXY_HOST) > 0 and len(PROXY_PORT) > 0:
        return requests.get(
            url,
            params,
            proxies=dict(
                http="socks5h://" + PROXY_HOST + ":" + PROXY_PORT,
                https="socks5h://" + PROXY_HOST + ":" + PROXY_PORT,
            ),
        )
    else:
        return requests.get(url, params)


def get_readable_size(size, decimal_places=2):
    for unit in ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]:
        if size < 1024.0 or unit == "PiB":
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"


def ensure_main_js():
    global raw_main_js
    if raw_main_js is None:
        raw_main_js = request(PIRATE_URL + "/static/main.js")


def fillin_categories():
    global raw_main_js
    ensure_main_js()

    raw_categories = ""
    for main_line in raw_main_js.iter_lines():
        # if re.search("function print_category", str(main_line)):
        raw_categories = main_line.decode("utf-8")

        if len(raw_categories) > 0:
            pattern = r"cc\[0\][ ]{0,1}==[ ]{0,1}[0-9]{1}\)[ ]{0,1}main[ ]{0,1}=[ ]{0,1}'[a-zA-Z0-9-_ \(\)\/]+'|cat[ ]{0,1}==[ ]{0,1}[0-9]{3}\)[ ]{0,1}return maintxt[ ]{0,1}\+[ ]{0,1}'[a-zA-Z0-9-_ \(\)\/]*'"
            matches = re.findall(pattern, raw_categories)
            for match in matches:
                if match.startswith("cc[0]"):
                    num = r"(?<!\[)[0-9]{1}(?!])"
                    ptn = r"(?<=')[a-zA-Z0-9-_ \(\)\/]*(?=')"
                    # num = "((?!cc\[0\]==)|(?!cc\[0\] == ))[0-9]{1}(?=\))"
                    # ptn = "((?!main=')|(?!main = ))[a-zA-Z0-9-_ \(\)\/]+(?=')"
                    cc_matches = re.findall(ptn, match)
                    num_matches = re.findall(num, match)
                    MAIN_CAT[num_matches[0]] = cc_matches[0]
                else:
                    num = "[0-9]{1,3}"
                    ptn = r"(?<=')[a-zA-Z0-9-_ \(\)\/]+(?=')"
                    cat_matches = re.findall(ptn, match)
                    num_matches = re.findall(num, match)
                    SUB_CAT[num_matches[0]] = cat_matches[0]


def get_trackers():
    global raw_main_js
    ensure_main_js()
    tracker_list = []

    raw_trackers = ""
    for main_line in raw_main_js.iter_lines():
        if re.search("function print_trackers", str(main_line)):
            raw_trackers = main_line.decode("utf-8")

    if len(raw_trackers) > 0:
        pattern = r"(?!encodeURIComponent\()[^\(]+(?=\))"
        matches = re.findall(pattern, raw_trackers)
        if len(matches) > 0:
            for tracker in matches:
                tracker_list.append(
                    urllib.parse.unquote(tracker.replace("'", ""))
                )

    return tracker_list


def get_category(category_num):
    try:
        main = MAIN_CAT[category_num[:1]]
        sub = SUB_CAT[category_num]
    except:
        main = "not"
        sub = "found"

    return main + " > " + sub


def get_search_result_list(keyword):
    converted_keyword = keyword.replace(" ", "+")
    search = {"q": converted_keyword, "cat": "0"}
    raw_search_results = request(PIRATE_API_URL + "/q.php", search)
    return json.loads(raw_search_results.content)


def search_tpb(keyword):
    print(f"SEARCH MAGNETS{keyword}")
    magnets = []

    fillin_categories()
    tracker_list = get_trackers()
    search_result = get_search_result_list(keyword)

    link_results = []
    names = []
    i = 0
    table = Table(title="PirateShip", box=box.ROUNDED)
    table.add_column("Nr.", justify="right", style="cyan")
    table.add_column("Type", justify="right", style="magenta")
    table.add_column("Name", justify="right", style="green")
    table.add_column("Nr.", justify="right", style="cyan")
    table.add_column("Size", justify="right", style="red")
    for search in search_result:
        magnet_link = MAGNET_FORMAT.format(
            search["info_hash"], urllib.parse.quote(search["name"])
        )
        href = MAGNET_FORMAT.format(
            search["info_hash"], urllib.parse.quote(search["name"])
        )

        # print(f'magnet_link={magnet_link}')
        for tracker in tracker_list:
            magnet_link = (
                magnet_link + "&tr=" + urllib.parse.quote_plus(tracker)
            )
        search["seeders"]
        print(f"search={search}")
        # print(f'seeds={seeds}')

        table.add_row(
            str(i),
            get_category(search["category"]),
            search["name"],
            str(i),
            get_readable_size(int(search["size"])),
        )
        link_results.append(magnet_link)
        names.append(search["name"])

        print("MAGNET CREATE")
        print(f"href={href}")
        print(f"magnet_url={magnet_link}")
        print(f'search["seeders"]={search["seeders"]}')
        print(f'int(search["size"])={int(search["size"])}')
        print(f'search["name"]={search["name"]}')
        print(
            f'get_category(search["category"])={get_category(search["category"])}'
        )
        magnet = Magnet(
            i,
            href,
            magnet_link,
            search["seeders"],
            int(search["size"]),
            search["name"],
            get_category(search["category"]),
        )
        # Store data in Magnet object
        magnets.append(magnet)

        # Move to next search result and update counter.
        i = i + 1

    console = Console()
    console.print(table)
    return magnets

    if len(link_results) > 0:
        console = Console()
        console.print(table)

        while 1:
            # option = input("选择编号或输入exit退出.")
            option = input("Select the number or type:exit to quit.")
            if option == "exit":
                exit(0)
            else:
                try:
                    selected_index = int(option)
                    if (
                        selected_index < len(link_results)
                        and selected_index >= 0
                    ):
                        print(
                            "名称:"
                            + names[selected_index]
                            + ",链接:"
                            + link_results[selected_index]
                        )
                        break
                    else:
                        raise ValueError("")
                except ValueError:
                    print("编号错误, 请重新输入")
                    print("Incorrect number, please try again")
                except KeyboardInterrupt:
                    exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        search_tpb(sys.argv[1])
    else:
        print("缺少搜索关键字!")
        print("Search words missing!")
