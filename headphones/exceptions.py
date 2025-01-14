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


class HeadphonesException(Exception):
    """
    Generic Headphones Exception - should never be thrown, only subclassed
    """


class NewzbinAPIThrottled(HeadphonesException):
    """
    Newzbin has throttled us, deal with it
    """


class SoftChrootError(HeadphonesException):
    """
    Fatal errors in SoftChroot module
    """

    pass
