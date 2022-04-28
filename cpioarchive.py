"""
cpioarchive: Support for cpio archives
Copyright (C) 2006 Ignacio Vazquez-Abrams

This library is free software; you can redistribute it and/or modify it under the terms of the GNU Lesser General 
Public License as published by the Free Software Foundation; either version 2.1 of the License, or (at your option) any 
later version.

This library is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied 
warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License for more 
details.

You should have received a copy of the GNU Lesser General Public License along with this library; if not, write to the 
Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
"""
import atexit


def version():
    """Returns the version number of the module."""
    from pkg_resources import get_distribution
    return get_distribution("cpioarchive").version


class CpioError(Exception):
    """Exception class for cpioarchive exceptions"""
    pass


class CpioEntry(object):
    """
    Information about a single file in a cpio archive. Provides a file-like
    interface for interacting with the entry.
    """
    def __init__(self, hdr, cpio, offset):
        if len(hdr) < 110:
            raise CpioError('cpio header too short')

        if not hdr.startswith(b'070701'):
            raise CpioError('cpio header invalid')

        namesize = int(hdr[94:102], 16)
        if len(hdr) < 110 + namesize:
            raise CpioError('cpio header too short')

        self.inode = int(hdr[6:14], 16)
        self.mode = int(hdr[14:22], 16)
        self.uid = int(hdr[22:30], 16)
        self.gid = int(hdr[30:38], 16)
        self.nlinks = int(hdr[38:46], 16)
        self.mtime = int(hdr[46:54], 16)
        self.devmajor = int(hdr[62:70], 16)
        self.devminor = int(hdr[70:78], 16)
        self.rdevmajor = int(hdr[78:86], 16)
        self.rdevminor = int(hdr[86:94], 16)
        self.checksum = int(hdr[102:110], 16)

        # Name of the file stored in the entry.
        self.name = hdr[110:110 + namesize - 1].decode("utf-8")
        # Size of the file stored in the entry.
        self.size = int(hdr[54:62], 16)

        self.datastart = offset + 110 + namesize
        self.datastart += (4 - (self.datastart % 4)) % 4
        self.curoffset = 0
        self.cpio = cpio
        self.closed = False
        self.fileobj = self.read(whole=True)

    def close(self):
        """
        Close this cpio entry. Further calls to methods will raise an
        exception.
        """
        self.closed = True

    def read(self, size=None, whole=False):
        """
        Read data from the entry.

        Args:
            size (int): Number of bytes to read (default: whole entry)
            whole (bool): Boolean for if the whole file should be read in

        Returns:
            bytes: The read in file object.
        """
        if self.closed:
            raise ValueError('read operation on closed file')

        if whole:
            start = self.cpio.file.tell()
            self.cpio.file.seek(self.datastart, 0)
            fileobj = self.cpio.file.read(self.size)
            self.cpio.file.seek(start, 0)

            return fileobj

        self.cpio.file.seek(self.datastart + self.curoffset, 0)

        if size and size < self.size - self.curoffset:
            ret = self.cpio.file.read(size)
        else:
            ret = self.cpio.file.read(self.size - self.curoffset)

        self.curoffset += len(ret)

        return ret

    def seek(self, offset, whence=0):
        """
        Move to new position within an entry.

        Args:
            offset (int): Byte count
            whence (int): Describes how offset is used.
              0: From beginning of file
              1: Forwards from current position
              2: Backwards from current position
              Other values are ignored.
        """
        if self.closed:
            raise ValueError('seek operation on closed file')

        if whence == 0:
            self.curoffset = offset
        elif whence == 1:
            self.curoffset += offset
        elif whence == 2:
            self.curoffset -= offset

        self.curoffset = min(max(0, self.curoffset), self.size)

    def tell(self):
        """Get current position within an entry"""
        if self.closed:
            raise ValueError('tell operation on closed file')

        return self.curoffset


class CpioArchive(object):
    def __init__(self, name=None, mode='r', fileobj=None):
        """
        Open a cpio archive.

        Args:
            name (str): Filename to open (default: open a file object instead)
            mode (str): Filemode to open the archive in (default: read-only)
            fileobj (obj): File object to use (default: open by filename instead)
        """
        self._infos = []
        self._ptr = 0
        self.closed = False
        self.entries = dict()

        if not mode == 'r':
            raise NotImplementedError()

        if name:
            self._readfile(name)
            self.external = False
        elif fileobj:
            self._readobj(fileobj)
            self.external = True

        atexit.register(self.close)

    def __iter__(self):
        return iter(self._infos)

    def __next__(self):
        return self.next()

    def close(self):
        """Close the CpioArchive. Also closes all associated entries."""
        if self.closed:
            return

        for entry in self._infos:
            entry.close()

        if not self.external:
            self.file.close()

        self.closed = True

    def next(self):
        """Return the next entry in the archive."""
        if self.closed:
            raise ValueError('next operation on closed file')

        if self._ptr > len(self._infos):
            raise StopIteration()

        ret = self._infos[self._ptr]
        self._ptr += 1
        return ret

    @classmethod
    def open(cls, name=None, mode='r', fileobj=None):
        """Open a cpio archive. Defers to CpioArchive.__init__()."""
        return cls(name, mode, fileobj)

    def _readfile(self, name):
        self._readobj(open(name, 'rb'))

    def _readobj(self, fileobj):
        self.file = fileobj

        start = self.file.tell()
        text = self.file.read(110)
        while text:
            namelen = int(text[94:102], 16)
            text += self.file.read(namelen)
            ce = CpioEntry(text, self, start)

            if not ce.name == "TRAILER!!!":
                self._infos.append(ce)
                self.entries.update({ce.name: ce})
            else:
                return

            # Skip the padding.
            self.file.seek((4 - (self.file.tell() - start) % 4) % 4, 1)
            # Skip the full length of the file.
            self.file.seek(self._infos[-1].size, 1)
            # Skip the padding.
            self.file.seek((4 - (self.file.tell() - start) % 4) % 4, 1)

            start = self.file.tell()
            text = self.file.read(110)
        else:
            raise CpioError('premature end of headers')
