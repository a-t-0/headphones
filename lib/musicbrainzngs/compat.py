# -*- coding: utf-8 -*-
# Copyright (c) 2012 Kenneth Reitz.

# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.

# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

"""
pythoncompat
"""


import sys

# -------
# Pythons
# -------

# Syntax sugar.
_ver = sys.version_info

#: Python 2.x?
is_py2 = (_ver[0] == 2)

#: Python 3.x?
is_py3 = (_ver[0] == 3)

# ---------
# Specifics
# ---------

if is_py2:
	from io import StringIO
	from urllib.request import HTTPPasswordMgr, HTTPDigestAuthHandler, Request, HTTPHandler, build_opener
	from urllib.error import HTTPError, URLError
	from http.client import BadStatusLine, HTTPException
	from urllib.parse import urlunparse
	from urllib.parse import urlencode

	bytes = str
	str = str
	str = str
elif is_py3:
	from io import StringIO
	from urllib.request import HTTPPasswordMgr, HTTPDigestAuthHandler, Request,\
								HTTPHandler, build_opener
	from urllib.error import HTTPError, URLError
	from http.client import HTTPException, BadStatusLine
	from urllib.parse import urlunparse, urlencode

	str = str
	bytes = bytes
	str = (str,bytes)
