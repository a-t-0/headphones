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
import re
from base64 import b16encode, b32decode
from hashlib import sha1

from bencode import decode as bdecode
from bencode import encode as bencode

import headphones
from headphones import (
    logger,
)


def read_torrent_name(torrent_file, default_name=None):
    """Read the torrent file and return the torrent name.

    If the torrent name cannot be determined, it will return the
    `default_name`.
    """

    # Open file
    try:
        with open(torrent_file, "rb") as fp:
            torrent_info = bdecode(fp.read())
    except OSError:
        logger.error("Unable to open torrent file: %s", torrent_file)
        return

    # Read dictionary
    if torrent_info:
        try:
            return torrent_info["info"]["name"]
        except KeyError:
            if default_name:
                logger.warning(
                    "Couldn't get name from torrent file: %s. "
                    "Defaulting to '%s'",
                    e,
                    default_name,
                )
            else:
                logger.warning(
                    "Couldn't get name from torrent file: %s. No "
                    "default given",
                    e,
                )

    # Return default
    return default_name


def calculate_torrent_hash(link, data=None):
    """Calculate the torrent hash from a magnet link or data.

    Raises a ValueError when it cannot create a torrent hash given the
    input data.
    """

    if link.startswith("magnet:"):
        torrent_hash = re.findall(r"urn:btih:([\w]{32,40})", link)[0]
        if len(torrent_hash) == 32:
            torrent_hash = b16encode(b32decode(torrent_hash)).lower()
    elif data:
        info = bdecode(data)[b"info"]
        torrent_hash = sha1(bencode(info)).hexdigest()
    else:
        raise ValueError(
            "Cannot calculate torrent hash without magnet link " "or data"
        )

    return torrent_hash.upper()


def get_seed_ratio(provider):
    """Return the seed ratio for the specified provider if applicable.

    Defaults to None in case of an error.
    """

    if provider == "rutracker.org":
        seed_ratio = headphones.CONFIG.RUTRACKER_RATIO
    elif provider == "Orpheus.network":
        seed_ratio = headphones.CONFIG.ORPHEUS_RATIO
    elif provider == "Redacted":
        seed_ratio = headphones.CONFIG.REDACTED_RATIO
    elif provider == "The Pirate Bay":
        seed_ratio = headphones.CONFIG.PIRATEBAY_RATIO
    elif provider == "Old Pirate Bay":
        seed_ratio = headphones.CONFIG.OLDPIRATEBAY_RATIO
    elif provider == "Waffles.ch":
        seed_ratio = headphones.CONFIG.WAFFLES_RATIO
    elif provider.startswith("Jackett_"):
        provider = provider.split("Jackett_")[1]
        if provider in headphones.CONFIG.TORZNAB_HOST:
            seed_ratio = headphones.CONFIG.TORZNAB_RATIO
        else:
            for torznab in headphones.CONFIG.get_extra_torznabs():
                if provider in torznab[0]:
                    seed_ratio = torznab[2]
                    break
    else:
        seed_ratio = None

    if seed_ratio is not None:
        try:
            seed_ratio = float(seed_ratio)
        except ValueError:
            logger.warn("Could not get seed ratio for %s" % provider)

    return seed_ratio


def get_year_from_release_date(release_date):
    try:
        year = release_date[:4]
    except TypeError:
        year = ""

    return year


def torrent_to_file(target_file, data):
    """Write torrent data to file, and change permissions accordingly.

    Will return None in case of a write error. If changing permissions
    fails, it will continue anyway.
    """

    # Write data to file
    try:
        with open(target_file, "wb") as fp:
            fp.write(data)
    except OSError as e:
        logger.error(f"Could not write `{target_file}`: {str(e)}")
        return

    # Try to change permissions
    if headphones.CONFIG.FILE_PERMISSIONS_ENABLED:
        try:
            os.chmod(target_file, int(headphones.CONFIG.FILE_PERMISSIONS, 8))
        except OSError as e:
            logger.warn(
                f"Could not change permissions for `{target_file}`: {e}"
            )
    else:
        logger.debug(
            f"Not changing file permissions for `{target_file}, since it is disabled"
        )

    # Done
    return True
