from scrapy.exporters import JsonItemExporter, JsonLinesItemExporter
import os
import time

# 标准 API 响应外层字段
API_CODE = 0
API_MSG = "success"

#继承JsonItemExporter自定义输出jsonObject
class JsonObjectItemExporter(JsonItemExporter):
    def start_exporting(self):
        now = time.time() #返回float数据
        #毫秒级时间戳
        stamp=int(round(now * 1000))
        start='{"code":%s,"msg":"%s","data":' % (API_CODE, API_MSG)
        self.file.write(bytes(start, encoding='utf-8'))
        self.file.write(b"[")
        self._beautify_newline()

    def finish_exporting(self):
        self._beautify_newline()
        self.file.write(b"]")
        stamp = int(round(time.time() * 1000))
        end = ',"timestamp":%s}' % stamp
        self.file.write(bytes(end, encoding='utf-8'))

class JsonObjectLinesItemExporter(JsonLinesItemExporter):
    def __init__(self, file, **kwargs):
        super().__init__(file, **kwargs)
        #毫秒级时间戳
        stamp=int(round(time.time() * 1000))
        start='{"code":%s,"msg":"%s","data":' % (API_CODE, API_MSG)
        self.file.write(bytes(start, encoding='utf-8'))
        self.file.write(b"[")
        self.first=True

    def export_item(self, item):
        if not self.first:
            self.file.write(b',')
        else:
            self.first=False
        super().export_item(item)

    def finish_exporting(self):
        self.file.write(b"]")
        stamp = int(round(time.time() * 1000))
        end = ',"timestamp":%s}' % stamp
        self.file.write(bytes(end, encoding='utf-8'))
