import ftplib
import logging
import csv
logger = logging.getLogger("logger")


class CDR(ftplib.FTP):
    def __init__(self, **kwargs):
        super(CDR, self).__init__(**kwargs)
        self.BinBuff = b""
        self.SplitBuff = []
        self.CDRpath = ""

    def _append_buf(self, data):
        self.BinBuff += data

    def _get_cdr_files(self):
        self.BinBuff = b""
        self.cwd(self.CDRpath)
        for filename in self.nlst():
            try:
                self.retrbinary('RETR %s' % filename, self._append_buf)
            except ftplib.error_perm as error:
                logger.error("File %s not loaded. Reason: %s", filename, error)
                yield filename, False
            yield filename, self.BinBuff.decode('utf-8')
            del self.BinBuff
            self.BinBuff = b""

    def _clear_cdr_dir(self):
        logger.debug("Try to clear %s", self.CDRpath)
        self.cwd(self.CDRpath)
        try:
            _ = list(map(self.delete, self.nlst()))
        except ftplib.error_perm as error:
            logger.warning("Can't clear ftp dir %s. Reason: %s", self.CDRpath, error)

    def parse_cdr_files(self):
        for filename, cdr_data in self._get_cdr_files():
            if not cdr_data:
                logger.warning("Can't get cdr data from file %s", filename)
                continue
            logger.debug("Trying to parse cdr data from %s", filename)
            csv_reader = csv.DictReader(cdr_data.split("\n"), delimiter=';')
            for row in csv_reader:
                yield row
        self._clear_cdr_dir()
        try:
            self.quit()
        except ftplib.error_perm as error:
            logger.warning("Can't quit from ftp error. Reason: %s", error)
            self.close()
