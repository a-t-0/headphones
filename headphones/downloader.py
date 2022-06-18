#  This file is part of Headphones.
#
#  Headphones is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Headphones is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Headphones.  If not, see <http://www.gnu.org/licenses/>.

import os
import random
import subprocess

from unidecode import unidecode

import headphones
from headphones import (
    classes,
    db,
    deluge,
    helpers,
    logger,
    notifiers,
    nzbget,
    qbittorrent,
    request,
    sab,
    transmission,
    utorrent,
)
from headphones.common import USER_AGENT
from headphones.searcher_helper import (
    calculate_torrent_hash,
    get_year_from_release_date,
    read_torrent_name,
    torrent_to_file,
)


def send_to_downloader(data, result, album, ruobj, TORRENT_TO_MAGNET_SERVICES):
    logger.info(
        f'Found best result from {result.provider}: <a href="{result.url}">'
        f"{result.title}</a> - {helpers.bytes_to_mb(result.size)}"
    )
    # Get rid of any dodgy chars here so we can prevent sab from renaming our downloads
    kind = result.kind
    seed_ratio = None
    torrentid = None

    if kind == "nzb":
        folder_name = helpers.sab_sanitize_foldername(result.title)

        if headphones.CONFIG.NZB_DOWNLOADER == 1:

            nzb = classes.NZBDataSearchResult()
            nzb.extraInfo.append(data)
            nzb.name = folder_name
            if not nzbget.sendNZB(nzb):
                return

        elif headphones.CONFIG.NZB_DOWNLOADER == 0:

            nzb = classes.NZBDataSearchResult()
            nzb.extraInfo.append(data)
            nzb.name = folder_name
            if not sab.sendNZB(nzb):
                return

            # If we sent the file to sab, we can check how it was renamed and insert that into the snatched table
            (replace_spaces, replace_dots) = sab.checkConfig()

            if replace_dots:
                folder_name = helpers.sab_replace_dots(folder_name)
            if replace_spaces:
                folder_name = helpers.sab_replace_spaces(folder_name)

        else:
            nzb_name = folder_name + ".nzb"
            download_path = os.path.join(
                headphones.CONFIG.BLACKHOLE_DIR, nzb_name
            )

            try:
                prev = os.umask(headphones.UMASK)

                with open(download_path, "wb") as fp:
                    fp.write(data)

                os.umask(prev)
                logger.info("File saved to: %s", nzb_name)
            except Exception as e:
                logger.error("Couldn't write NZB file: %s", e)
                return
    else:
        folder_name = "{} - {} [{}]".format(
            unidecode(album["ArtistName"]).replace("/", "_"),
            unidecode(album["AlbumTitle"]).replace("/", "_"),
            get_year_from_release_date(album["ReleaseDate"]),
        )

        # Blackhole
        if headphones.CONFIG.TORRENT_DOWNLOADER == 0:

            # Get torrent name from .torrent, this is usually used by the torrent client as the folder name
            torrent_name = (
                helpers.replace_illegal_chars(folder_name) + ".torrent"
            )
            download_path = os.path.join(
                headphones.CONFIG.TORRENTBLACKHOLE_DIR, torrent_name
            )

            if result.url.lower().startswith("magnet:"):
                if headphones.CONFIG.MAGNET_LINKS == 1:
                    try:
                        if headphones.SYS_PLATFORM == "win32":
                            os.startfile(result.url)
                        elif headphones.SYS_PLATFORM == "darwin":
                            subprocess.Popen(
                                ["open", result.url],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                            )
                        else:
                            subprocess.Popen(
                                ["xdg-open", result.url],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                            )

                        # Gonna just take a guess at this..... Is there a better way to find this out?
                        folder_name = result.title
                    except Exception as e:
                        logger.error("Error opening magnet link: %s" % str(e))
                        return
                elif headphones.CONFIG.MAGNET_LINKS == 2:
                    # Procedure adapted from CouchPotato
                    torrent_hash = calculate_torrent_hash(result.url)

                    # Randomize list of services
                    services = TORRENT_TO_MAGNET_SERVICES[:]
                    random.shuffle(services)
                    headers = {"User-Agent": USER_AGENT}

                    for service in services:

                        data = request.request_content(
                            service % torrent_hash, headers=headers
                        )
                        if data:
                            if not torrent_to_file(download_path, data):
                                return
                            # Extract folder name from torrent
                            folder_name = read_torrent_name(
                                download_path, result.title
                            )

                            # Break for loop
                            break
                    else:
                        # No service succeeded
                        logger.warning(
                            "Unable to convert magnet with hash "
                            "'%s' into a torrent file.",
                            torrent_hash,
                        )
                        return
                elif headphones.CONFIG.MAGNET_LINKS == 3:
                    torrent_to_file(download_path, data)
                    return
                else:
                    logger.error(
                        "Cannot save magnet link in blackhole. "
                        "Please switch your torrent downloader to "
                        "Transmission, uTorrent or Deluge, or allow Headphones "
                        "to open or convert magnet links"
                    )
                    return
            else:

                if not torrent_to_file(download_path, data):
                    return

                # Extract folder name from torrent
                folder_name = read_torrent_name(download_path, result.title)
                if folder_name:
                    logger.info("Torrent folder name: %s" % folder_name)

        elif headphones.CONFIG.TORRENT_DOWNLOADER == 1:
            logger.info("Sending torrent to Transmission")

            # Add torrent
            if result.provider == "rutracker.org":
                torrentid = transmission.addTorrent("", data)
            else:
                torrentid = transmission.addTorrent(result.url)

            if not torrentid:
                logger.error(
                    "Error sending torrent to Transmission. Are you sure it's running?"
                )
                return

            folder_name = transmission.getName(torrentid)
            if folder_name:
                logger.info("Torrent name: %s" % folder_name)
            else:
                logger.error("Torrent name could not be determined")
                return

            # Set Seed Ratio
            seed_ratio = get_seed_ratio(result.provider)
            if seed_ratio is not None:
                transmission.setSeedRatio(torrentid, seed_ratio)

        elif headphones.CONFIG.TORRENT_DOWNLOADER == 3:  # Deluge
            logger.info("Sending torrent to Deluge")

            try:
                # Add torrent
                if result.provider == "rutracker.org":
                    torrentid = deluge.addTorrent("", data)
                else:
                    torrentid = deluge.addTorrent(result.url)

                if not torrentid:
                    logger.error(
                        "Error sending torrent to Deluge. Are you sure it's running? Maybe the torrent already exists?"
                    )
                    return

                # This pauses the torrent right after it is added
                if headphones.CONFIG.DELUGE_PAUSED:
                    deluge.setTorrentPause({"hash": torrentid})

                # Set Label
                if headphones.CONFIG.DELUGE_LABEL:
                    deluge.setTorrentLabel({"hash": torrentid})

                # Set Seed Ratio
                seed_ratio = get_seed_ratio(result.provider)
                if seed_ratio is not None:
                    deluge.setSeedRatio(
                        {"hash": torrentid, "ratio": seed_ratio}
                    )

                # Set move-to directory
                if (
                    headphones.CONFIG.DELUGE_DONE_DIRECTORY
                    or headphones.CONFIG.DOWNLOAD_TORRENT_DIR
                ):
                    deluge.setTorrentPath({"hash": torrentid})

                # Get folder name from Deluge, it's usually the torrent name
                folder_name = deluge.getTorrentFolder({"hash": torrentid})
                if folder_name:
                    logger.info("Torrent folder name: %s" % folder_name)
                else:
                    logger.error("Torrent folder name could not be determined")
                    return

            except Exception as e:
                logger.error("Error sending torrent to Deluge: %s" % str(e))

        elif headphones.CONFIG.TORRENT_DOWNLOADER == 2:
            logger.info("Sending torrent to uTorrent")

            # Add torrent
            if result.provider == "rutracker.org":
                ruobj.utorrent_add_file(data)
            else:
                utorrent.addTorrent(result.url)

            # Get hash
            torrentid = calculate_torrent_hash(result.url, data)
            if not torrentid:
                logger.error("Torrent id could not be determined")
                return

            # Get folder
            folder_name = utorrent.getFolder(torrentid)
            if folder_name:
                logger.info("Torrent folder name: %s" % folder_name)
            else:
                logger.error("Torrent folder name could not be determined")
                return

            # Set Label
            if headphones.CONFIG.UTORRENT_LABEL:
                utorrent.labelTorrent(torrentid)

            # Set Seed Ratio
            seed_ratio = get_seed_ratio(result.provider)
            if seed_ratio is not None:
                utorrent.setSeedRatio(torrentid, seed_ratio)
        else:  # if headphones.CONFIG.TORRENT_DOWNLOADER == 4:
            logger.info("Sending torrent to QBiTorrent")

            # Add torrent
            if result.provider == "rutracker.org":
                if qbittorrent.apiVersion2:
                    qbittorrent.addFile(data)
                else:
                    ruobj.qbittorrent_add_file(data)
            else:
                qbittorrent.addTorrent(result.url)

            # Get hash
            torrentid = calculate_torrent_hash(result.url, data)
            torrentid = torrentid.lower()
            if not torrentid:
                logger.error("Torrent id could not be determined")
                return

            # Get name
            folder_name = qbittorrent.getName(torrentid)
            if folder_name:
                logger.info("Torrent name: %s" % folder_name)
            else:
                logger.error("Torrent name could not be determined")
                return

            # Set Seed Ratio
            # Oh my god why is this repeated again for the 100th time
            seed_ratio = get_seed_ratio(result.provider)
            if seed_ratio is not None:
                qbittorrent.setSeedRatio(torrentid, seed_ratio)

    myDB = db.DBConnection()
    myDB.action(
        'UPDATE albums SET status = "Snatched" WHERE AlbumID=?',
        [album["AlbumID"]],
    )
    myDB.action(
        "INSERT INTO snatched VALUES (?, ?, ?, ?, DATETIME('NOW', 'localtime'), "
        "?, ?, ?, ?)",
        [
            album["AlbumID"],
            result.title,
            result.size,
            result.url,
            "Seed_Snatched" if seed_ratio and torrentid else "Snatched",
            folder_name,
            kind,
            torrentid,
        ],
    )

    # notify
    artist = album[1]
    albumname = album[2]
    rgid = album[6]
    title = artist + " - " + albumname
    provider = result.provider
    if provider.startswith(("http://", "https://")):
        provider = provider.split("//")[1]
    name = folder_name if folder_name else None

    if headphones.CONFIG.GROWL_ENABLED and headphones.CONFIG.GROWL_ONSNATCH:
        logger.info("Sending Growl notification")
        growl = notifiers.GROWL()
        growl.notify(name, "Download started")
    if headphones.CONFIG.PROWL_ENABLED and headphones.CONFIG.PROWL_ONSNATCH:
        logger.info("Sending Prowl notification")
        prowl = notifiers.PROWL()
        prowl.notify(name, "Download started")
    if (
        headphones.CONFIG.PUSHOVER_ENABLED
        and headphones.CONFIG.PUSHOVER_ONSNATCH
    ):
        logger.info("Sending Pushover notification")
        prowl = notifiers.PUSHOVER()
        prowl.notify(name, "Download started")
    if (
        headphones.CONFIG.PUSHBULLET_ENABLED
        and headphones.CONFIG.PUSHBULLET_ONSNATCH
    ):
        logger.info("Sending PushBullet notification")
        pushbullet = notifiers.PUSHBULLET()
        pushbullet.notify(name, "Download started")
    if headphones.CONFIG.JOIN_ENABLED and headphones.CONFIG.JOIN_ONSNATCH:
        logger.info("Sending Join notification")
        join = notifiers.JOIN()
        join.notify(name, "Download started")
    if headphones.CONFIG.SLACK_ENABLED and headphones.CONFIG.SLACK_ONSNATCH:
        logger.info("Sending Slack notification")
        slack = notifiers.SLACK()
        slack.notify(name, "Download started")
    if (
        headphones.CONFIG.TELEGRAM_ENABLED
        and headphones.CONFIG.TELEGRAM_ONSNATCH
    ):
        logger.info("Sending Telegram notification")
        from headphones import cache

        c = cache.Cache()
        album_art = c.get_artwork_from_cache(None, rgid)
        telegram = notifiers.TELEGRAM()
        message = "Snatched from " + provider + ". " + name
        telegram.notify(message, "Snatched: " + title, rgid, image=album_art)
    if (
        headphones.CONFIG.TWITTER_ENABLED
        and headphones.CONFIG.TWITTER_ONSNATCH
    ):
        logger.info("Twitter notifications temporarily disabled")
        # logger.info("Sending Twitter notification")
        # twitter = notifiers.TwitterNotifier()
        # twitter.notify_snatch(name)
    if headphones.CONFIG.NMA_ENABLED and headphones.CONFIG.NMA_ONSNATCH:
        logger.info("Sending NMA notification")
        nma = notifiers.NMA()
        nma.notify(snatched=name)
    if (
        headphones.CONFIG.PUSHALOT_ENABLED
        and headphones.CONFIG.PUSHALOT_ONSNATCH
    ):
        logger.info("Sending Pushalot notification")
        pushalot = notifiers.PUSHALOT()
        pushalot.notify(name, "Download started")
    if (
        headphones.CONFIG.OSX_NOTIFY_ENABLED
        and headphones.CONFIG.OSX_NOTIFY_ONSNATCH
    ):
        from headphones import cache

        c = cache.Cache()
        album_art = c.get_artwork_from_cache(None, rgid)
        logger.info("Sending OS X notification")
        osx_notify = notifiers.OSX_NOTIFY()
        osx_notify.notify(
            artist,
            albumname,
            "Snatched: " + provider + ". " + name,
            image=album_art,
        )
    if headphones.CONFIG.BOXCAR_ENABLED and headphones.CONFIG.BOXCAR_ONSNATCH:
        logger.info("Sending Boxcar2 notification")
        b2msg = "From " + provider + "<br></br>" + name
        boxcar = notifiers.BOXCAR()
        boxcar.notify("Headphones snatched: " + title, b2msg, rgid)
    if headphones.CONFIG.EMAIL_ENABLED and headphones.CONFIG.EMAIL_ONSNATCH:
        logger.info("Sending Email notification")
        email = notifiers.Email()
        message = "Snatched from " + provider + ". " + name
        email.notify("Snatched: " + title, message)
