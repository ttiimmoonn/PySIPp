import ftplib
import logging
import time
import csv
logger = logging.getLogger("logger")


class CDR(ftplib.FTP):
    def __init__(self, **kwargs):
        super(CDR, self).__init__(**kwargs)
        self.BinBuff = []

    def _clear_cdr_dir(self, path):
        logger.debug("Try to clear %s", path)
        try:
            _ = list(map(self.delete, self.nlst()))
        except ftplib.error_perm as error:
            logger.warning("Can't clear ftp dir %s. Reason: %s", self.CDRpath, error)
        except ftplib.error_temp as error:
            logger.warning("Can't clear ftp dir %s. Reason: %s", self.CDRpath, error)

    def _remove_file(self, filename):
        try:
            self.delete(filename)
        except ftplib.error_perm as error:
            logger.warning("Can't remove file %s. Reason: %s", filename, error)
        except ftplib.error_temp as error:
            logger.warning("Can't remove file %s. Reason: %s", filename, error)

    def _append_buf(self, data):
        self.BinBuff.append(data)

    def _download_file(self, filename):
        try:
            logger.info("Loading cdr file %s.", filename)
            self.retrbinary('RETR %s' % filename, self._append_buf, blocksize=65535)
        except ftplib.error_perm as error:
            logger.error("File %s not loaded. Reason: %s", filename, error)
            return False
        return True

    def _get_cdr_file(self, path, filename, attempts=5):
        for attempt in range(attempts):
            if not self._download_file(filename):
                print(self.nlst())
                time.sleep(1)
                self.cwd(path)
                continue
            else:
                return True
        return False

    def close_connection(self):
        try:
            self.quit()
        except ftplib.error_perm as error:
            logger.warning("Can't quit from ftp error. Reason: %s", error)
            self.close()

    def parse_cdr_file(self, path, filename):
        self.cwd(path)
        if not self._get_cdr_file(path, filename):
            self.cwd("/")
            raise StopIteration
        cdr_data = b"".join(self.BinBuff).decode('utf-8')
        csv_reader = csv.DictReader(cdr_data.split("\n"), delimiter=';')
        for row in csv_reader:
            yield row
        self._remove_file(filename)
        self.cwd("/")
        self.BinBuff = []

    def parse_all_cdr_files(self, path):
        self.cwd(path)
        for filename in self.nlst():
            logger.info("Parsing cdr file: %s", filename)
            if not self._get_cdr_file(path, filename):
                self.cwd("/")
                raise StopIteration
            logger.debug("Trying to parse cdr data from %s", filename)
            cdr_data = b"".join(self.BinBuff).decode('utf-8')
            csv_reader = csv.DictReader(cdr_data.split("\n"), delimiter=';')
            for row in csv_reader:
                yield row
            del csv_reader
            self.BinBuff = []
        self._clear_cdr_dir(path)