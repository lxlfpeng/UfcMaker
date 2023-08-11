import PyRSS2Gen
import datetime
import os

class NoOutput:
    def __init__(self):
        pass
    def publish(self, handler):
        pass
# 用于解决PyRSS2Gen的desc转义字符的问题 https://stackoverflow.com/questions/5371704/python-generated-rss-outputting-raw-html/5400662#5400662
class CDATARSS(PyRSS2Gen.RSSItem):
    def __init__(self, **kwargs):
        PyRSS2Gen.RSSItem.__init__(self, **kwargs)

    def publish(self, handler):
        self.do_not_autooutput_description = self.description
        self.description = NoOutput() # This disables the Py2GenRSS "Automatic" output of the description, which would be escaped.
        PyRSS2Gen.RSSItem.publish(self, handler)

    def publish_extensions(self, handler):
        handler._write('<%s><![CDATA[%s]]></%s>' % ("description", self.do_not_autooutput_description, "description"))

class RssMaker:
    def __init__(self, title, link, description):
        self.title = title
        self.link = link
        self.description = description

    def makeRss(self, rssList, path):
        if len(rssList)==0:
            return
        rssItems = []
        for content in rssList:
            rssItem = CDATARSS(
                title=content['title'],
                link=content['link'],
                description=content['description'],
                pubDate=datetime.datetime.now())
            rssItems.append(rssItem)
        rss = PyRSS2Gen.RSS2(
            title=self.title,
            link=self.link,
            description=self.description,
            lastBuildDate=datetime.datetime.now(),
            items=rssItems
        )
        # 取出路径
        dir_path = os.path.dirname(path)
        # 判断路径是否存在,不存在则创建路径
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        # 将内容进行写入
        rss.write_xml(open(path, "w", encoding='utf-8'), encoding='utf-8')

    def get_html_str(self,item):
        html="""<div style="display: flex;">
	        <div  style="width: 50%; height: auto;">
	              <h2>Red Player</h2>
                  <p><strong>Name:</strong> {redPlayerName}</p>
                  <p><strong>Nationality:</strong>{redPlayerCountry}</p>
                  <p><strong>CountryFlag:</strong>{redPlayerCountryEmoji}</p>
                  <p><strong>Rank:</strong> {redPlayerRank}</p>
                  <p><strong>odds:</strong> {redPlayerOdds}</p>
                  <div style="height: 200px;overflow: hidden;">
                    <img src="{redPlayerBack}" alt="Image Red"/>
                  </div>                  
	        </div>
	        <div  style="width: 50%; height: auto;">
	              <h2>Red Player</h2>                 
                  <p><strong>Name:</strong> {bluePlayerName}</p>
                  <p><strong>Nationality:</strong>{bluePlayerCountry}</p>
                  <p><strong>CountryFlag:</strong>{bluePlayerCountryEmoji}</p>
                  <p><strong>Rank:</strong> {bluePlayerRank}</p>
                  <p><strong>odds:</strong> {bluePlayerOdds}</p>
                  <div style="height: 200px;overflow: hidden;">
                    <img src="{bluePlayerBack}" alt="Image Blue"/>
                  </div>                                    
	        </div>
            </div>""".format(redPlayerBack=item['redPlayerBack'], 
                             redPlayerName=item["redPlayerName"], 
                             redPlayerCountry=item["redPlayerCountry"], 
                             redPlayerCountryEmoji=item["redPlayerCountryEmoji"], 
                             redPlayerRank=item["redPlayerRank"], 
                             redPlayerOdds=item["redPlayerOdds"], 
                             bluePlayerBack=item["bluePlayerBack"], 
                             bluePlayerName=item["bluePlayerName"], 
                             bluePlayerCountry=item["bluePlayerCountry"], 
                             bluePlayerCountryEmoji=item["bluePlayerCountryEmoji"], 
                             bluePlayerRank=item["bluePlayerRank"], 
                             bluePlayerOdds=item["bluePlayerOdds"])
        return html
