import time

from ..quasarzone_cleaner import Cleaner
from PyQt5 import QtCore


class CleanerThread(QtCore.QThread):
    event_signal = QtCore.pyqtSignal(dict)

    def __init__(self, captcha_signal):
        super().__init__()
        self.cleaner: Cleaner
        self.captcha_signal = captcha_signal
        self.del_list = []
        self.p_type = ''
        self.del_all = True
        self.count = 0

        self.captcha_flag = False

        self.captcha_signal.connect(self.checkCaptcha)

    def setCleaner(self, cleaner):
        self.cleaner = cleaner

    def setDelInfo(self, del_list, p_type, del_all,count):
        self.del_list = del_list
        self.p_type = p_type
        self.del_all = del_all
        self.count = count

    def checkCaptcha(self):
        self.captcha_flag = False

    def deleteEvent(self, event):
        self.event_signal.emit(event)
        if event['type'] == 'captcha':
            while self.captcha_flag:
                pass

    def delete(self, gno,index,cnt):

        self.cleaner.aggregatePosts(gno, self.p_type,self.event_signal,self.count)


    def run(self):

        for index, gno in enumerate(self.del_list):
            self.delete(gno,index,len(self.del_list))
            time.sleep(5)

        self.event_signal.emit({'type': 'complete'})
