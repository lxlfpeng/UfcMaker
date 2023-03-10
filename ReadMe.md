# 概述
### Scrapy是什么?
[Scrapy](https://github.com/scrapy/scrapy)，是一个用**Python实现**的用于**抓取网站**并从其**网页中提取结构化数据**的**应用框架**。Scrapy用途广泛，可以用于**数据挖掘、监测和自动化测试**。

### Scrapy运行的要求
- Python 3.7+运行环境
- 可以工作在: Linux, Windows, macOS, BSD

### Scrapy的构成
Scrapy 是用纯python编写的，它依赖于几个关键的python包：
- lxml：一个高效的XML和HTML解析器
- parsel ：一个写在lxml上面的html/xml数据提取库,
- w3lib ：用于处理URL和网页编码的多用途帮助程序
- twisted：异步网络框架
- cryptography 和 pyOpenSSL ：处理各种网络级安全需求

### Scrapy的架构
![](https://img-blog.csdnimg.cn/5b5842e123b340528c99b328b8d863bc.png)
Scrapy框架主要由五大组件组成，它们分别是调度器(Scheduler)、下载器(Downloader)、爬虫（Spider）和实体管道(Item Pipeline)、Scrapy引擎(Scrapy Engine)。
- Schedule：调度器。接收从引擎发过来的requests，并将他们入队。初始爬取url和后续在页面里爬到的待爬取url放入调度器中，等待被爬取。调度器会自动去掉重复的url。
- Downloader：下载器。负责获取页面数据，并提供给引擎，而后提供给spider,Scrapy下载器是建立在twisted这个高效的异步模型上的。
- Spider：爬虫。用户定制自己的爬虫(通过定制正则表达式等语法)，用于从特定的网页中分析response并提取item(实体)。也可以从中提取出链接,让Scrapy继续抓取下一个页面。将每个spider负责处理一个特定(或 一些)网站。
- ItemPipeline：负责处理被spider提取出来的item。当页面被爬虫解析所需的数据存入Item后，将被发送到Pipeline，并经过设置好次序,主要的功能是持久化实体、验证实体的有效性、清除不需要的信息。 
- ScrapyEngine：引擎。负责控制数据流在系统中所有组件中流动，并在相应动作发生时触发事件。 此组件相当于爬虫的“大脑”，是 整个爬虫的调度中心。 

### Scrapy工作流程
1. 爬虫项目正式启动。
2. 引擎向爬虫程序索要第一批要爬取的URL，交给调度器入队列。
3. 调度器处理请求后出队列，通过下载器中间件交给下载器去下载。
4. 下载器得到响应对象后，通过蜘蛛中间件交给爬虫程序。
5. 数据交给管道文件去入库处理。
6. 对于需要跟进的URL，再次交给调度器入队列，如此循环。

# 使用Scrapy
本文以以豆瓣热门电影排行榜为例,讲解如何使用Scrapy爬取网页数据。
### 安装Scrapy
```
pip install Scrapy
```
或者使用国内镜像源进行安装:
```
pip install scrapy -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Scrapy创建项目
使用scrapy创建项目，项目名为douban:
```
scrapy startproject douban
```
此时生成了一个douban项目文件夹:
```
douban                 # 项目文件夹 
├── douban             # 项目目录 
│   ├── items.py       # 爬虫项目的数据容器文件，用来定义要获取的数据。
│   ├── middlewares.py # 中间件文件，配置所有中间件 
│   ├── pipelines.py   # 爬虫项目的管道文件，用来对items中的数据进行进一步的加工处理。
│   ├── settings.py    # douban爬虫项目的设置文件，包含了爬虫项目的设置信息。
│   └── spiders        # Spider类文件夹，所有的Spider均在此存放
└── scrapy.cfg         # 整个Scrapy的配置文件，由Scrapy自动生成
```

### Scrapy创建爬虫
要创建Spider爬虫，需要进入刚才创建的Scrapy目录中，然后在运行以下命令：
```
scrapy genspider <爬虫名字> <允许爬取的域名>
```
可以进入douban文件夹中创建爬虫:
```
scrapy genspider doubanhot movie.douban.com
```
这个新建的爬虫文件会被放入douban/spiders文件夹中。DoubanhotSpider初始内容如下:
```
import scrapy
class DoubanhotSpider(scrapy.Spider):                      # 自定义spider类，继承自scrapy.Spider
    name = "doubanhot"                                     # 爬虫名，用来区分不同的Spider，当运行爬虫项目时使用
    allowed_domains = ["movie.douban.com"]                 # 允许爬取的域名，非本域的URL地址会被过滤
    start_urls = ["'https://movie.douban.com/top250'"]     # 爬虫项目启动时起始的URL地址

    def parse(self, response):                             # 解析数据方法
        pass

```
在Scrapy项目中所有的Spider类都必须得继承scrapy.Spider，其中name、start_urls以及parse成员方法是每个Spider类必须要声明的。更多的Spider属性以及成员方法可以[查看文档](https://docs.scrapy.org/en/latest/topics/spiders.html?highlight=Spider)

### 修改爬虫相关配置
使用爬虫时我们需要对请求头等相关进行配置,以便能获取到数据,在Scrapy中通过settings.py文件可以配置相关功能:
- BOT_NAME：项目名
- USER_AGENT：默认是注释的，这个东西非常重要，如果不写很容易被判断为电脑，简单点洗一个Mozilla/5.0即可
- ROBOTSTXT_OBEY：是否遵循机器人协议，默认是true，需要改为false，否则很多东西爬不了
- CONCURRENT_REQUESTS：最大并发数，很好理解，就是同时允许开启多少个爬虫线程 默认为16
- DOWNLOAD_DELAY：下载延迟时间，单位是秒，控制爬虫爬取的频率，根据你的项目调整，不要太快也不要太慢，默认是3秒，即爬一个停3秒，设置为1秒性价比较高，如果要爬取的文件较多，写零点几秒也行
- COOKIES_ENABLED：是否保存COOKIES，默认关闭，开机可以记录爬取过程中的COKIE，非常好用的一个参数
- DEFAULT_REQUEST_HEADERS：默认请求头，上面写了一个USER_AGENT，其实这个东西就是放在请求头里面的，这个东西可以根据你爬取的内容做相应设置。
- ITEM_PIPELINES：{ '项目目录名.pipelines.类名': 优先级} 项目管道，300为优先级，越低越爬取的优先度越高
- DOWNLOADER_MIDDLEWARES = { '项目目录名.middlewares.类名': 优先级} :下载器中间件

常见的改动如下:
```
# 设置USER_AGENT
USER_AGENT = 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/535.1 (KHTML, like Gecko) Chrome/14.0.835.163 Safari/535.1'

# 是否遵循robots协议，一定要设置为False
ROBOTSTXT_OBEY = False 

# 最大并发量，默认为16
CONCURRENT_REQUESTS = 32 	

# 下载延迟时间，每隔多长时间发一个请求(降低数据抓取频率)
DOWNLOAD_DELAY = 3

# 是否启用Cookie，默认禁用，取消注释即为开启了Cookie
COOKIES_ENABLED = False

# 请求头，类似于requests.get()方法中的 headers 参数
DEFAULT_REQUEST_HEADERS = {
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Language': 'en',
}
```
### 运行爬虫
**方式一:**
在终端项目文件夹中输入scrapy crawl 爬虫文件名
```
scrapy crawl doubanhot
```
**方式二:**
在最外层的项目文件中创建run.py
```
# 在run.py文件中
from scrapy import cmdline
cmdline.execute('scrapy crawl doubanhot'.split())
```

### 编写爬虫相关逻辑
```
import scrapy
class DoubanhotSpider(scrapy.Spider):
    name = "doubanhot"
    allowed_domains = ['movie.douban.com']
    start_urls = ['https://movie.douban.com/top250']

    def parse(self, response):
        info = response.xpath('//div[@class="info"]')
        for i in info:                
            title = i.xpath("./div[1]/a/span[1]/text()").extract_first()
            introduce = i.xpath("./div[2]/p[1]//text()").extract()  # 获取全部内容
            introduce = "".join(j.strip() for j in [i.replace("\\xa0", '') for i in introduce])  # 整理信息
            print("电影名:",title)
            print("电影简介:",introduce)
    
```
运行爬虫可以看到已经可以抓取到数据进行输出了。
### 将爬取到的数据提取到结构化数据（Item）
为了避免拼写错误或者定义字段错误，我们可以在items.py文件中定义好字段 item 定义结构化的数据字段，用来存储爬取到的数据，有点像python里面的字典，但是提供了一些而外的保护减少错误,打开items.py可以通过创建一个 scrapy.Item 类，并且定义类型为 scrapy.Field 的类属性来定义一个 Item （可以理解成类似于ORM的映射关系）
```
class DoubanItem(scrapy.Item):
    title = scrapy.Field()  # 标题
    introduce = scrapy.Field()  # 介绍
```
>注意：在对item进行赋值时，只能通过item['key']=value的方式进行赋值，不可以通过item.key=value的方式赋值。
修改爬虫相关逻辑:
```
import scrapy
from ..items import DoubanItem

class DoubanhotSpider(scrapy.Spider):
    name = "doubanhot"
    allowed_domains = ['movie.douban.com']
    start_urls = ['https://movie.douban.com/top250']

    def parse(self, response):
        info = response.xpath('//div[@class="info"]')
        for i in info:
            item = DoubanItem()                
            title = i.xpath("./div[1]/a/span[1]/text()").extract_first()
            introduce = i.xpath("./div[2]/p[1]//text()").extract()  # 获取全部内容
            introduce = "".join(j.strip() for j in [i.replace("\\xa0", '') for i in introduce])  # 整理信息
            item["title"] = title
            item["introduce"] = introduce
            # 将获取的数据交给 pipeline
            yield item    

```
有人可能会说为什么要多此一举定义一个字典呢？

当我们在获取到数据的时候，使用不同的item来存放不同的数据，在把数据交给pipeline的时候，可以通过isinstance(item,Test1Item)来判断数据属于哪个item，进行不同的数据(item)处理。
例如我们获取到京东、淘宝、拼多多的数据时，我们可以items.py文件中定义好对应的字段，具体代码如下：

```
import scrapy
class JingdongItem(scrapy.Item):
    text= scrapy.Field()
    author = scrapy.Field()

class TaobaoItem(scrapy.Item):
    text= scrapy.Field()
    author = scrapy.Field()

class PddItem(scrapy.Item):
    text= scrapy.Field()
    author = scrapy.Field()
```

定义好字段后，这是我们通过在pipeline.py文件中编写代码，对不同的item数据进行区分，具体代码如下：

```
from douban.items import JingdongItem
from douban.items import TaobaoItem
from douban.items import PddItem
class Test1Pipeline:
    def process_item(self, item, spider):
        if isinstance(item,JingdongItem):
            print(item)
        if isinstance(item,TaobaoItem):
            print(item)
        if isinstance(item,PddItem):
            print(item)                
```

首先我们通过导入我们的items.py，通过isinstance()函数来就可以成功获取到对应的item数据了。

### 使用管道对数据进行处理
pipelines.py介绍

Item Pipeline为项目管道，当Item生成后，它就会自动被送到Item Pipeline进行处理，我们常用Item Pipeline来做以下操作：

* 清理HTML数据；
* 验证爬取数据，检测爬取字段；
* 查看并丢弃重复内容；
* 将爬取结果保存到数据库。

pipelines.py内容如下所示：

```
from itemadapter import ItemAdapter

class Test1Pipeline:
    def process_item(self, item, spider):
        return item
```

在process_item()方法中，传入了两个参数，一个参数是item，每次Spider生成的Item都会作为参数传递过来。另一个参数是spider，就是Spider的实例对象。

完成pipeline代码后，需要在setting.py中设置开启，开启方式很简单，只要把setting.py内容中的以下代码的注释取消即可：

```
ITEM_PIPELINES = {
    'test1.pipelines.Test1Pipeline': 300,
}
```

其中：

- test1.pipelines.Test1Pipeline是pipeline的位置；
- 300是pipeline的权重。数字越小对应的权重就越大

注意：

* pipeline的权重越小优先级越高；
* pipeline中的process_item()方法名不能修改为其他的名称；
* pipeline能够定义多个。

当我们有多个spider爬虫时，为了满足不同的spider爬虫需求，这时可以定义不同的pipeline处理不同的item内容；当一个spider的内容可能要做不同的操作时，例如存入不同的数据库中，这时可以定义不同的pipeline处理不同的item操作。

例如当我们有多个spider爬虫时，可以通过pipeline.py编写代码定义多个pipeline，具体代码如下：

```
class JingdongPipeline:
    def process_item(self, item, spider):
        if spider.name=="jingdong":
        	print(item)
        return item

class TaobaoPipeline:
    def process_item(self, item, spider):
        if spider.name=="taobao":
        	print(item)
        return item
```

这样我们就可以处理到对应的spider爬虫传递过来的数据了。

定义好pipeline后，我们要在settings.py中设置pipeline权重，也就是那个pipeline先运行，具体代码如下：

```
ITEM_PIPELINES = {
   'douban.pipelines.JingdongPipeline': 300,
   'douban.pipelines.TaobaoPipeline': 301,
}
```

process_item(item, spider)
process_item()是必须要实现的方法，被定义的ItemPipeline会默认调用这个方法对Item进行处理。比如，我们可以进行数据处理或者将数据写入到数据库等操作。它必须返回Item类型的值或者抛出一个DropItem异常

close_spider(spider)
open_spider()方法是在Spider开启的时候被自动调用的。在这里我们可以做一些初始化操作，如开启数据库连接等。其中，参数spider就是被开启的Spider对象。

close_spider(spider)
close_spider()方法是在Spider关闭的时候自动调用的。在这里我们可以做一些收尾工作，如关闭数据库连接等。其中，参数spider就是被关闭的Spider对象。

### 数据传输到pipeline中,进行数据处理
在上面我们已经提取到想要的数据，接下来将数据传到pipeline中，传输很简单，我们只需要使用yield，代码如下：

```
yield item
```

没错，只要在spider爬虫中写入这一行代码即可，那么为什么要使用yield呢？，我用return不能行吗？行，但yield是让整个函数变成一个生成器，每次遍历的时候挨个读到内存中，这样不会导致内存的占用量瞬间变高。

### 实现翻页

我们成功获取到了一页数据了，那么问题来了，如何实现翻页呢，方法有很多种，我们主要介绍两种。

**第一种：使用start_requests()方法**

我们通过在spider爬虫中，也就是我们创建的firstspider.py中添加以下代码，具体代码如下：

```
def start_requests(self):
    for i in range(1,3):
        url=f'https://quotes.toscrape.com/page/{i}/'
        yield scrapy.Request(url=url,callback=self.parse)
```

**第二种：在parse()方法中实现翻页**

我们可以通过parse()方法中实现翻页，具体代码如下：

```
def parse(self, response):
    for i in range(2,3):
        url = f'https://quotes.toscrape.com/page/{i}/'
        yield scrapy.Request(url=url,callback=self.parse)
```

大家可以发现，上面两种翻页方式都差不多，只是一个在start_requests()方法实现，一个在parse()方法实现。

但都要使用scrapy.Request()方法，该方法能构建一个requests，同时指定提取数据的callback函数

```
scrapy.Requeset(url,callback,method='GET',headers,cookies,meta,dont_filter=False)
```

其中：
* url：表示爬取的url链接；
* callback：指定传入的url交给哪个解析函数去处理；
* headers：请求头；
* cookies：用于识别用户身份、进行回话跟踪而存储在用户本地终端上的数据；
* meta：实现在不同的解析函数中传递数据；
* dont_filter：让scrapy的去重不会过滤当前url，scrapy默认有url去重的功能。

### 保存数据
我们已经获取到数据而且实现了翻页，接下来是保存数据。

**保存在文件中**

当我们要把数据保存成文件的时候，不需要任何额外的代码，只要执行如下代码即可：

```
scrapy crawl spider爬虫名 -o xxx.json    		  # 保存为JSON文件
scrapy crawl spider爬虫名 -o xxx.jl或jsonlines    # 每个Item输出一行json
scrapy crawl spider爬虫名 -o xxx.csv    	      # 保存为csv文件
scrapy crawl spider爬虫名 -o xxx.xml			  # 保存为xml文件
```

想要保存为什么格式的文件，只要修改后缀就可以了。

**保存MongoDB中**

当我们要把数据保存在MongoDB等数据库的时候，就要使用Item Pipeline模块了，也就是说要在pipeline.py中编写代码，具体代码如下所示：

```
from pymongo import  MongoClient
client=MongoClient()
collection=client["test1"]["firstspider"]

class Test1Pipeline:
    def process_item(self, item, spider):
        collection.insert(item)
        return item
```

首先我们导入MongoClient模块并实例化MongoClient，创建一个集合，然后在process_item()方法中使用insert()方法把数据插入MongoDB数据库中。

###  图片下载
[文档地址](https://scrapy-chs.readthedocs.io/zh_CN/0.24/topics/images.html#)

#### 方式一 使用自带的pipeline下载
在setting.py中配置图片下载:
```
import os
# 配置数据保存路径，为当前工程目录下的 images 目录中
project_dir = os.path.abspath(os.path.dirname(__file__))
IMAGES_STORE = os.path.join(project_dir, 'images')
# 过期天数
IMAGES_EXPIRES = 90  # 90天内抓取的都不会被重抓

# 自定义文件url字段
FILES_URLS_FIELD = 'field_name_for_your_files_urls'
# 自定义结果字段    
FILES_RESULT_FIELD = 'field_name_for_your_processed_files'
# 自定义图片url字段   
IMAGES_URLS_FIELD = 'field_name_for_your_images_urls'
# 结果字段        
IMAGES_RESULT_FIELD = 'field_name_for_your_processed_images'    

# IMAGES_MIN_HEIGHT = 100  # 过滤图片的最小高度
# IMAGES_MIN_WIDTH = 100   # 过滤图片的最小宽度
# MEDIA_ALLOW_REDIRECTS = True    是否重定向
# 设置管道为默认的下载管道
ITEM_PIPELINES = {
   'scrapy.pipelines.images.ImagesPipeline': 1,
}
```
通过上面的配置文件我们可以配置如下内容:
- 将下载图片转换成通用的JPG和RGB格式
- 避免重复下载
- 缩略图生成
- 图片大小过滤
可能会缺少PIL模块,需要安装pillow图片包
```
pip3 install pillow
```
#### 方式二 重写pipeline实现图片保存功能
如果有特殊的要求就要重写pipeline(类似重命名或者分目录)
1. 在setting.py中配置图片下载
```
import os
# 配置数据保存路径，为当前工程目录下的 images 目录中
project_dir = os.path.abspath(os.path.dirname(__file__))
IMAGES_STORE = os.path.join(project_dir, 'images')
# 过期天数
IMAGES_EXPIRES = 90  # 90天内抓取的都不会被重抓
 
# IMAGES_MIN_HEIGHT = 100  # 图片的最小高度
# IMAGES_MIN_WIDTH = 100   # 图片的最小宽度

# 这里所不同的是需要创建自己的图片下载管道
ITEM_PIPELINES = {
   'scrapy.pipelines.ImagesDownloadPipeline': 1,
}
```

2. 编写下载的Pipeline
需要实现图片的下载，我们需要让自己的pipeline继承scrapy框架的ImagesPipeline。scrapy框架在此pipeline中封装了图片下载操作（并发下载，速度可以保证）。由于scrapy封装十分完善，我们只需要覆写get_media_requests函数，将图片的url通过yield Request(item['url'])传递给下载操作：当Item传递到ImagePipeline后，将调用Scrapy调度器和下载器完成image_urls中的URL的调度和下载。ImagePipeline会自动高优先级抓取这些url，与此同时，item会被锁定直到图片抓取完毕才解锁。这些图片下载完成后，图片下载路径、url和校验等信息会被填充到images字段中。

`ImagesPipeLine`：图片下载的模块

在`pipeline`中，编写代码（已知，item里面传输的是图片的下载地址）

```
import logging
import scrapy
from itemadapter import ItemAdapter
from scrapy.pipelines.images import ImagesPipeline


# 继承ImagesPipeLine
class ImagesDownloadPipeline(ImagesPipeline):
    # 根据图片地址，发起请求
    def get_media_requests(self, item, info):
        # item["src] 里面存储的是图片的地址
        src = item["src"]  
        # 对图片发起请求
        yield scrapy.Request(url = src,meta={'item':item})  
    
    # 指定图片的名字 下载下来的图片命名是以校验码来命名的，该方法实现保持原有图片命名
    def file_path(self, request, response=None, info=None, *, item=None):
        # 接收meta参数
        item = request.meta['item']
        # 设置文件名字  
        return request.url.split("/")[-1]  
        # 在settings中设置 IMAGES_STORE = "./imags"  设置图片保存的文件夹

    # 返回数据给下一个即将被执行的管道类下载结果，二元组定义如下：(success, image_info_or_failure)。
        第一个元素表示图片是否下载成功；第二个元素是一个字典。
        如果success=true，image_info_or_error词典包含以下键值对。失败则包含一些出错信息。
         字典内包含* url：原始URL * path：本地存储路径 * checksum：校验码

	def file_path(self,request,response=None, info=None):
        # 调用原方法，获得原路径（full/xxx.xxx)
        originPath = super(MyFilesPipeline, self).file_path(request, response, info)
        title = request.meta['name']  #取出定义好的文件名
        #原方法返回的路径默认为：'full/xxxxx.xxx'，利用正则表达替换路径和文件名
        #本示例将文件直接保存在settings定义的文件夹根目录下，并重命名
        newPath = re.sub('full/.+\.', title + '.', originPath)  #注意加点
        return newPath  #用新定义的路径代替默认路径

    def item_completed(self, results, item, info):
        image_paths = [x['path'] for ok, x in results if ok]
        if not image_paths:
            raise DropItem("Item contains no images")   # 如果没有路径则抛出异常
        item['image_paths'] = image_paths
        return item
```

在这个py文件中，我们定义了ImagesDownloadPipeline这个类，这个类继承于ImagesPipeline。在这里定义了两个函数，一个是根据传入的urls来发起请求，请求完成后直接调用item_completed函数来处理得到的图片。get_media_requests函数中，发起请求的时候，不需要指定回调函数，ImagePipeline会自动调用item_completed函数来处理。

在scrapy爬虫框架启动后，文件会根据setting.py中设置的IMAGES_STORE，将图片保存在IMAGES_STORE/full目录下。
默认情况下，使用ImagePipeline组件下载图片的时候，图片名称是以图片URL的SHA1值进行保存的。
如果想进行更改，请参考：[scrapy框架的ImagesPipeline下载图片如何保持原文件名](https://segmentfault.com/q/1010000000413334)

#### 其他方式
不继承scrapy类自带文件的类中书写下载图片的方式有
* 1、方式一:直接使用`urllib`库中的`request`请求图片的`url`地址
  ```
  import os
  from urllib import request
  
  class CarPipeline(object):
      """
      下载图片的pipeline
      """
  
      def __init__(self):
          # 生成最外面的文件夹
          self.path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'images')
          if not os.path.exists(self.path):
              os.makedirs(self.path)
  
      def process_item(self, item, spider):
          if spider.name == 'car':
              category = item['category']
              urls = item['urls']
  
              # 生成分类的文件夹
              category_path = os.path.join(self.path, category)
              if not os.path.exists(category_path):
                  os.makedirs(category_path)
  
              # 遍历全部的url地址写入
              for url in urls:
                  imgage_name = url.split('_')[-1]
                  request.urlretrieve(url, os.path.join(category_path, imgage_name))
              return item
  ```
* 2、方式二:借用`requests`库请求`Spider`过来的`url`地址,请求,手动写入到本地
  ```
  import os
  import requests
  
  class CarPipeline(object):
      """
      手动下载图片
      """
  
      def __init__(self):
          # 生成最外面的文件夹
          self.path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'images')
          if not os.path.exists(self.path):
              os.makedirs(self.path)
  
      def process_item(self, item, spider):
          if spider.name == 'car':
              category = item['category']
              urls = item['urls']
  
              # 生成分类的文件夹
              category_path = os.path.join(self.path, category)
              if not os.path.exists(category_path):
                  os.makedirs(category_path)
              # 遍历全部的url地址写入
              for url in urls:
                  imgage_name = url.split('_')[-1]
                  response = requests.get(url)
                  with open(os.path.join(category_path, imgage_name), 'wb') as f:
                      f.write(response.content)
              return item
  ```
# 下载文件
和下载图片一样


# 常见问题
### 使用scrapy框架 出现ModuleNotFoundError: No module named ‘attrs‘问题
终端输入
```
pip install attrs --upgrade
```

### Scrapy之Request函数回调未执行解决方案
两种方法能够使 requests 不被过滤: 
1. 在 allowed_domains 中加入 url ；
2. 在 scrapy.Request() 函数中将参数 dont_filter=True 设置为 True。


### Scrapy 将数据保存为标准 Json 格式文件的方法
在 Scrapy 中保存 json 文件有以下 3 种方式：

1. 直接创建并写入 json 文件，将数据写入其中
2. 使用 Scrapy.exporters 中自带的 **JsonItemExporter**进行导出操作
3. 使用 Scrapy.exporters 中自带的 **JsonLinesItemExporter**进行导出操作

但，Scrapy 框架提供的这两个 json 导出模块，均 **存在各自的问题** ：

1. JsonItemExporter
   必须先将爬虫爬取下来的 **所有数据存放在内存** 中，待爬虫完成后，再一次性写入文件。
   这种方式，可以输出标准的 json 格式文件，但是如果数据量巨大，会 **大量占用内存** 。
2. JsonLinesItemExporter
   这种方式，每次拿到数据都直接写入文件，占用内存少，但是输出的结果 **并不是标准的 Json 格式文件** ，无法通过 Json 将文件内容解析出来。

---

于是，下面首先介绍，第一种方式，直接创建并将数据写入 json 文件，

## 一、直接创建并写入 json 文件

1. 在 Scrapy 框架的 pipeline 写入如下内容
   ```
   import os
   import codecs
   import json
   
   
   class SpiderPipeline(object):
       # 构造方法（初始化对象时执行的方法）
       def __init__(self):
           # 必须使用 w+ 模式打开文件，以便后续进行 读写操作（w+模式，意味既可读，亦可写）
           # 注意：此处打开文件使用的不是 python 的 open 方法，而是 codecs 中的 open 方法
           self.json_file = codecs.open('data.json', 'w+', encoding='UTF-8')
   
       # 爬虫开始时执行的方法
       def open_spider(self, spider):
           # 在爬虫开始时，首先写入一个 '[' 符号，构造一个 json 数组
           # 为使得 Json 文件具有更高的易读性，我们辅助输出了 '\n'（换行符）
           self.json_file.write('[\n')
   
       # 爬虫 pipeline 接收到 Scrapy 引擎发来的 item 数据时，执行的方法
       def process_item(self, item, spider):
           # 将 item 转换为 字典类型，并编码为 json 字符串，写入文件
           # 为使得 Json 文件具有更高的易读性，我们辅助输出了 '\t'（制表符） 与 '\n'（换行符）
           item_json = json.dumps(dict(item), ensure_ascii=False)
           self.json_file.write('\t' + item_json + ',\n')
           return item
   
       # 爬虫结束时执行的方法
       def close_spider(self, spider):
           # 在结束后，需要对 process_item 最后一次执行输出的 “逗号” 去除
           # 当前文件指针处于文件尾，我们需要首先使用 SEEK 方法，定位到文件尾前的两个字符（一个','(逗号), 一个'\n'(换行符)）的位置
           self.json_file.seek(-2, os.SEEK_END)
           # 使用 truncate() 方法，将后面的数据清空
           self.json_file.truncate()
           # 重新输出'\n'，并输出']'，与 open_spider(self, spider) 时输出的 '[' 相对应，构成一个完整的数组格式
           self.json_file.write('\n]')
           # 关闭文件
           self.json_file.close()
   复制代码
   ```
2. 输出示例
   ```
   [	{"title": "用户拒绝授权小程序使用通讯地址API的问题和解决方法", "author_nickName": "KOSS", "content": "小程序中正确使用通讯地址这个开发接口的流程：思路："},	{"title": "房产小程序开发", "author_nickName": "Right Here Waiting", "content": "房产小程序：任何关于楼盘价格问题、户型问题、周边设施问题都可以小程序上直接沟通。房产小程序可以很好的帮助哪些懒人解决看房问题，楼盘价格及周边设施都可以详细的展示，用户也可以直接在小程序上面预约，然后在实地看房。"}]
   复制代码
   ```

## 二、使用 JsonItemExporter 写入 Json 文件

1. 在 Scrapy 框架的 pipeline 写入如下内容
   ```
   # 导入 JsonItemExporter
   from scrapy.exporters import JsonItemExporter
   
   
   class SpiderPipeline(object):
       # 构造方法（初始化对象时执行的方法）
       def __init__(self):
           # 使用 'wb' （二进制写模式）模式打开文件
           self.json_file = open('data.json', 'wb')
           # 构建 JsonItemExporter 对象，设定不使用 ASCII 编码，并指定编码格式为 'UTF-8'
           self.json_exporter = JsonItemExporter(self.json_file, ensure_ascii=False, encoding='UTF-8')
           # 声明 exporting 过程 开始，这一句也可以放在 open_spider() 方法中执行。
           self.json_exporter.start_exporting()
   
       # 爬虫 pipeline 接收到 Scrapy 引擎发来的 item 数据时，执行的方法
       def process_item(self, item, spider):
           # 将 item 存储到内存中
           self.json_exporter.export_item(item)
           return item
   
       def close_spider(self, spider):
           # 声明 exporting 过程 结束，结束后，JsonItemExporter 会将收集存放在内存中的所有数据统一写入文件中
           self.json_exporter.finish_exporting()
           # 关闭文件
           self.json_file.close()
   复制代码
   ```
2. 输出示例
   ```
   [{"title": "用户拒绝授权小程序使用通讯地址API的问题和解决方法", "author_nickName": "KOSS", "content": "小程序中正确使用通讯地址这个开发接口的流程：思路："},{"title": "房产小程序开发", "author_nickName": "Right Here Waiting", "content": "房产小程序：任何关于楼盘价格问题、户型问题、周边设施问题都可以小程序上直接沟通。房产小程序可以很好的帮助哪些懒人解决看房问题，楼盘价格及周边设施都可以详细的展示，用户也可以直接在小程序上面预约，然后在实地看房。"}]
   复制代码
   ```

## 二、使用 JsonLinesItemExporter 写入 json 文件

1. 在 Scrapy 框架的 pipeline 写入如下内容
   ```
   # 导入 JsonLinesItemExporter
   from scrapy.exporters import JsonLinesItemExporter
   
   
   class SpiderPipeline(object):
       # 构造方法（初始化对象时执行的方法）
       def __init__(self):
           # 使用 'wb' （二进制写模式）模式打开文件
           self.json_file = open('data.json', 'wb')
           # 构建 JsonLinesItemExporter 对象，设定不使用 ASCII 编码，并指定编码格式为 'UTF-8'
           self.json_exporter = JsonLinesItemExporter(self.json_file, ensure_ascii=False, encoding='UTF-8')
           # 声明 exporting 过程 开始，这一句也可以放在 open_spider() 方法中执行。
           self.json_exporter.start_exporting()
   
       # 爬虫 pipeline 接收到 Scrapy 引擎发来的 item 数据时，执行的方法
       def process_item(self, item, spider):
           # 将 item 直接写入文件中
           self.json_exporter.export_item(item)
           return item
   
       def close_spider(self, spider):
           # 声明 exporting 过程 结束，结束后，JsonItemExporter 会将收集存放在内存中的所有数据统一写入文件中
           self.json_exporter.finish_exporting()
           # 关闭文件
           self.json_file.close()
   复制代码
   ```
2. 输出示例
   ```
   {"title": "用户拒绝授权小程序使用通讯地址API的问题和解决方法", "author_nickName": "KOSS", "content": "小程序中正确使用通讯地址这个开发接口的流程：思路："}
   {"title": "房产小程序开发", "author_nickName": "Right Here Waiting", "content": "房产小程序：任何关于楼盘价格问题、户型问题、周边设施问题都可以小程序上直接沟通。房产小程序可以很好的帮助哪些懒人解决看房问题，楼盘价格及周边设施都可以详细的展示，用户也可以直接在小程序上面预约，然后在实地看房。"}
   复制代码
   ```

## 三、三种方式对比

| **序号** | **方式**        | **内存占用情况** | **是否为标准 json 格式** | **易读性** |
| ---------------- | ----------------------- | ------------------------ | -------------------------------- | ------------------ |
| 1              | 直接创建并写入文件    | 低                     | 是                             | 高               |
| 2              | JsonItemExporter      | 高                     | 是                             | 低               |
| 3              | JsonLinesItemExporter | 低                     | 否                             | 较低             |


### 自定义写入

```
# -*- coding: utf-8 -*-
 
# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://doc.scrapy.org/en/latest/topics/item-pipeline.html
import codecs
import json
import os
# 自定义文件写入pipelines
class HongxiuPipeline(object):
    def __init__(self):
        # 用来打开本地的json文件，w+有的话打开，没有的话创建打开
        self.file=codecs.open(filename='book.json',mode='w+',encoding='utf-8')
        self.file.write('"book_list":[')
    # 如果需要将数据写入到本地json或者是数据库中，必须用process_item()函数
    def process_item(self, item, spider):
        # 先将item对象转化为一个字典对象
        res=dict(item)
        # 再将字典对象转化为Json字符串
        str=json.dumps(res,ensure_ascii=False)
        # 写入json字符串
        self.file.write(str)
        # 添加换行符
        self.file.write(',\n')
        # 返回一个item对象，供后续的pipeline对这个item进行处理
        return item
    def open_spider(self,spider):
        # 爬虫程序开启时，这句话会被输出
        print('爬虫开始')
    def close_spider(self,spider):
        # 爬虫程序关闭时，这个函数会被调用，然后输出这句话
        print('爬虫结束')
        # 将json文件中的最后的字符',\'删除掉
        # -1表示偏移量至文件的末尾，SEEK_END定位到
          # 文章的最后一个字符
        # 这个取出的是换行符\n
        self.file.seek(-1,os.SEEK_END)
        self.file.truncate()
        # 这个去除的是','号
        self.file.seek(-1,os.SEEK_END)
        self.file.truncate()
        # 加上列表的另一半部分
        self.file.write(']')
        self.file.close()
```



## 语法:
(1) response对象
响应的是二进制文件response . body
响应的是字符串response.text
响应的是请求的urlresponse.ur1
response.status响应的状态码
(2) response的解析:
response.xpath() (常用)使用xpath路径查询特定元素，返回一个selector列表对象
response.css(使用css selector查询元素，返回一个selector列表对象获取内容 : response.css('#su::text').extract first()获取属性 : response.css('#su::attr(“value”)').extract first()(3) selector对象 (通过xpath方法调用返回的是seletor列表)
extract(
提取selector对象的值如果提取不到值 那么会报错使用xpath请求到的对象是一个selector对象，需要进一步使用extract()方法拆
包，转换为unicode字符串
extract first()提取seletor列表中的第一个值如果提取不到值 会返回一个空值返回第一个解析到的值，如果列表为空，此种方法也不会报错，会返回一个空值
xpath()
css()
注意:每一个selector对象可以再次的去使用xpath或者css方法


# 日志
scrapy也使用python日志级别分类
- CRITICAL - 严重错误
- ERROR - 一般错误
- WARNING - 警告信息
- INFO - 一般信息
- DEBUG - 调试信息

我配置的时候用了WARNING等级，那么我将100个1和这是一个异常定义为WARNING输出的时候（logging.warning），则高于或者等于该等级的信息就能输出到我的日志中，低于该级别的信息则输出不到我的日志信息中

```
import logging

logging.baseConfig(filename="", filemode="", format="", datefmt="", stylefmt="", style="", level="", stream="")

logging.info(msg, *args, **kw)
loggin.debug(msg, *args, **kw)
logging.warning(msg, *args, **kw)
```

级别的作用
首先，根据严重程度排序：DEBUG < INFO < WARNING < ERROR < CRITICAL

具体每个级别表示什么含义可以按照自己的习惯来处理。如果设置 level=logging.DEBUG，那么以上所有的信息都会被输出到日志。如果设置级别为WARNING，那么只有WARNING及以上会输出到日志。


如何在scrapy中配置日志呢？

在scrapy中使用日志很简单，只需在settings.py中设置LOG_FILE和LOG_LEVEL两个配置项就可以了
```
# 一般在使用时只会设置LOG_FILE和LOG_LEVEL两个配置项，其他配置项使用默认值
# 指定日志的输出文件
LOG_FILE
# 是否使用日志，默认为True
LOG_ENABLED
# 日志使用的编码，默认为UTF-8
LOG_ENCODING
# 日志级别，如果设置了，那么高于该级别的就会输入到指定文件中
LOG_LEVEL
# 设置日志的输出格式
LOG_FORMAT
# 设置日志的日期输出格式
LOG_DATEFORMAT
# 设置标准输出是否重定向到日志文件中，默认为False,如果设置为True,那么print("hello")就会被重定向到日志文件中
LOG_STDOUT
# 如果设置为True,只会输出根路径，不会输出组件，默认为FALSE
LOG_SHORT_NAMES
```

### 在Spider中使用log日志

每个蜘蛛实例都有一个 **记录器** ，可以按如下方式使用 –

```
import scrapy 

class LogSpider(scrapy.Spider):  
   name = 'logspider' 
   start_urls = ['http://dmoz.com']  
   def parse(self, response): 
      self.logger.info('Parse function called on %s', response.url)
```

在上面的代码中，记录器是使用 Spider 的名称创建的，但您可以使用 Python 提供的任何自定义记录器，如下面的代码所示 –

```
import logging
import scrapy

logger = logging.getLogger('customizedlogger')
class LogSpider(scrapy.Spider):
   name = 'logspider'
   start_urls = ['http://dmoz.com']

   def parse(self, response):
      logger.info('Parse function called on %s', response.url)
```



### 查看日志信息

异常次数
```
 # 前面四个是抓取过程中出现的异常次数
 'downloader/exception_count': 28,
 'downloader/exception_type_count/twisted.internet.error.ConnectionRefusedError': 25,
 'downloader/exception_type_count/twisted.web._newclient.ResponseFailed': 2,
 'downloader/exception_type_count/twisted.web._newclient.ResponseNeverReceived': 1,
```
此次抓取一共出现了28次异常，以及异常类别汇总。

总的请求大小和总的返回大小
```
# 字节数
'downloader/request_bytes': 135350,
'downloader/response_bytes': 6441438,
```
总的请求数和返回数
```
 'downloader/request_count': 288,
 'downloader/request_method_count/GET': 288,
 'downloader/response_count': 260,
 'downloader/response_status_count/200': 256,
 'downloader/response_status_count/404': 4,
```
可知总共请求了288次，其中28次异常无response。260次有response，正常返回的有256次，找不到页面4次。

开始和结束时间
```
'start_time': datetime.datetime(2017, 12, 16, 3, 9, 15, 789205)
'finish_time': datetime.datetime(2017, 12, 16, 3, 15, 6, 948483)

```
可以算出一共花了多少时间。

Item处理次数
```
'item_scraped_count': 246
```
这个比较重要，是item处理的条数，可知，此次抓取250个电影详情页，有4部电影主页是404（不知道是不是豆瓣的bug，这四部电影的主页有时有有时无，奇葩！），总共处理了246部电影（更新或插入数据库）。260条请求中有10个是TOP250的列表分页，共10页。这10页并无item处理。260 = 10 + 246 + 4。

重试的次数
```
 'retry/count': 28,
 'retry/reason_count/twisted.internet.error.ConnectionRefusedError': 25,
 'retry/reason_count/twisted.web._newclient.ResponseFailed': 2,
 'retry/reason_count/twisted.web._newclient.ResponseNeverReceived': 1,
```
Scrapy的重试次数和优先级可以在setting中配置。


我们需要设置的地方只在`settings.py`文件夹中进行设置就可以了。

```python
LOG_LEVEL = 'DEBUG'
to_day = datetime.datetime.now()
log_file_path = 'log/scrapy_{}_{}_{}.log'.format(to_day.year, to_day.month, to_day.day)
LOG_FILE = log_file_path
```

这里我设置`scrapy log`日志为`DEBUG`级别，也就是屏幕上输出的级别，最低的级别，如果你想让你自己所打印的`log`出现在`log`文件中，你可以在`spider`里面这样用

### 怎么样将scrapy每个模块的打印信息输出到同一个日志文件中？
2、普通项目中

　　a)建立一个通用的log_a.py

[![复制代码](https://common.cnblogs.com/images/copycode.gif)](javascript:void(0); "复制代码")

```
# coding = utf-8
import  logging
logging.basicConfig(level=logging.DEBUG,
                format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                datefmt='%a, %d %b %Y %H:%M:%S',
                filename='myapp.log',
                filemode='w')

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    logger.info("this is a log ")
```

[![复制代码](https://common.cnblogs.com/images/copycode.gif)](javascript:void(0); "复制代码")

b) log_b.py文件使用通用的log_a.py

```
# coding = utf-8
from log_a import logger

if __name__ == '__main__':
    logger.warning("b文件")
```

### 自定义日志格式

可以通过扩展 [`<span class="pre" _istranslated="1">LogFormatter</span>`](https://docs.scrapy.org/en/latest/topics/logging.html#scrapy.logformatter.LogFormatter "scrapy.logformatter.LogFormatter") 类并[`<span class="pre" _istranslated="1">LOG_FORMATTER</span>`](https://docs.scrapy.org/en/latest/topics/settings.html#std-setting-LOG_FORMATTER)指向新类，为不同的操作设置自定义日志格式。

*.class*刮擦.日志格式化器.日志格式化程序[[来源]](https://docs.scrapy.org/en/latest/_modules/scrapy/logformatter.html#LogFormatter)[¶](https://docs.scrapy.org/en/latest/topics/logging.html#scrapy.logformatter.LogFormatter "Permalink to this definition")用于为不同操作生成日志消息的类。

所有方法都必须返回一个字典，列出参数，以及这些参数将用于构造日志消息时 叫。`<span class="pre">level</span>``<span class="pre">msg</span>``<span class="pre">args</span>``<span class="pre">logging.log</span>`

方法输出的字典键：

* `<span class="pre">level</span>`是该操作的日志级别，您可以使用 Python 日志记录库中的日志级别：、、 和 。`<span class="pre">logging.DEBUG</span>``<span class="pre">logging.INFO</span>``<span class="pre">logging.WARNING</span>``<span class="pre">logging.ERROR</span>``<span class="pre">logging.CRITICAL</span>`
* `<span class="pre">msg</span>`应该是可以包含不同格式占位符的字符串。 这个字符串，使用提供的格式，将是长消息 对于该操作。`<span class="pre">args</span>`
* `<span class="pre">args</span>`应为元组或字典，其格式占位符为 。 最终日志消息计算为 。`<span class="pre">msg</span>``<span class="pre">msg</span><span> </span><span class="pre">%</span><span> </span><span class="pre">args</span>`

如果用户想要自定义如何 每个操作都会被记录下来，或者如果他们想完全省略它。为了省略 记录该方法必须返回的操作。`<span class="pre">LogFormatter</span>``<span class="pre">None</span>`

下面是有关如何创建自定义日志格式化程序以降低 从管道中删除项时的日志消息：

```
class PoliteLogFormatter(logformatter.LogFormatter):
    def dropped(self, item, exception, response, spider):
        return {
            'level': logging.INFO, # lowering the level from logging.WARNING
            'msg': "Dropped: %(exception)s" + os.linesep + "%(item)s",
            'args': {
                'exception': exception,
                'item': item,
            }
        }
```

已爬行（请求、响应、蜘蛛**)**[[来源]](https://docs.scrapy.org/en/latest/_modules/scrapy/logformatter.html#LogFormatter.crawled)[¶](https://docs.scrapy.org/en/latest/topics/logging.html#scrapy.logformatter.LogFormatter.crawled "Permalink to this definition")在爬网程序找到网页时记录消息。

download_error（failure， request， spider， errmsg=None**)**[[来源]](https://docs.scrapy.org/en/latest/_modules/scrapy/logformatter.html#LogFormatter.download_error)[¶](https://docs.scrapy.org/en/latest/topics/logging.html#scrapy.logformatter.LogFormatter.download_error "Permalink to this definition")记录来自蜘蛛的下载错误消息（通常来自 引擎）。

**版本 2.0 中的新功能。**

丢弃（项目、异常、响应、蜘蛛**)**[[来源]](https://docs.scrapy.org/en/latest/_modules/scrapy/logformatter.html#LogFormatter.dropped)[¶](https://docs.scrapy.org/en/latest/topics/logging.html#scrapy.logformatter.LogFormatter.dropped "Permalink to this definition")在项通过项管道时丢弃项时记录消息。

item_error（项目、异常、响应、蜘蛛**)**[[来源]](https://docs.scrapy.org/en/latest/_modules/scrapy/logformatter.html#LogFormatter.item_error)[¶](https://docs.scrapy.org/en/latest/topics/logging.html#scrapy.logformatter.LogFormatter.item_error "Permalink to this definition")当项目在传递时导致错误时记录消息 通过项目管道。

**版本 2.0 中的新功能。**

抓取（项目，响应，蜘蛛**)**[[来源]](https://docs.scrapy.org/en/latest/_modules/scrapy/logformatter.html#LogFormatter.scraped)[¶](https://docs.scrapy.org/en/latest/topics/logging.html#scrapy.logformatter.LogFormatter.scraped "Permalink to this definition")记录当项目被蜘蛛抓取时的消息。

spider_error（失败、请求、响应、蜘蛛**)**[[来源]](https://docs.scrapy.org/en/latest/_modules/scrapy/logformatter.html#LogFormatter.spider_error)[¶](https://docs.scrapy.org/en/latest/topics/logging.html#scrapy.logformatter.LogFormatter.spider_error "Permalink to this definition")记录来自蜘蛛的错误消息。

**版本 2.0 中的新功能。**

### 高级定制

由于 Scrapy 使用 stdlib 日志记录模块，因此您可以使用 STDLIB 日志记录的所有功能。

例如，假设您正在抓取一个返回许多 HTTP 404 和 500 响应，并且您希望隐藏所有消息，如下所示：

```
2016-12-16 22:00:06 [scrapy.spidermiddlewares.httperror] INFO: Ignoring
response <500 https://quotes.toscrape.com/page/1-34/>: HTTP status code
is not handled or not allowed
```

首先要注意的是记录器名称 - 它在括号中：.如果只是这样，LOG_SHORT_NAMES可能会设置为 True;将其设置为 False 并重新运行 爬行。`<span class="pre">[scrapy.spidermiddlewares.httperror]</span>``<span class="pre">[scrapy]</span>`

接下来，我们可以看到消息具有 INFO 级别。要隐藏它 我们应该将日志记录级别设置为高于 INFO;信息是警告之后的下一个级别。这是可以做到的 例如，在蜘蛛的方法中：`<span class="pre">scrapy.spidermiddlewares.httperror</span>``<span class="pre">__init__</span>`

```
import logging
import scrapy


class MySpider(scrapy.Spider):
    # ...
    def __init__(self, *args, **kwargs):
        logger = logging.getLogger('scrapy.spidermiddlewares.httperror')
        logger.setLevel(logging.WARNING)
        super().__init__(*args, **kwargs)
```

如果您再次运行此蜘蛛，则来自记录器的 INFO 消息将消失。`<span class="pre">scrapy.spidermiddlewares.httperror</span>`

您还可以按[`<span class="pre" _istranslated="1">日志记录</span>`](https://docs.python.org/3/library/logging.html#logging.LogRecord "(in Python v3.11)")数据筛选日志记录。为 例如，您可以使用子字符串或按消息内容筛选日志记录，或者 正则表达式。创建[`<span class="pre" _istranslated="1">日志记录。过滤器</span>`](https://docs.python.org/3/library/logging.html#logging.Filter "(in Python v3.11)")子类 并为其配备正则表达式模式 过滤掉不需要的邮件：

```
import logging
import re

class ContentFilter(logging.Filter):
    def filter(self, record):
        match = re.search(r'\d{3} [Ee]rror, retrying', record.message)
        if match:
            return False
```

项目级筛选器可以附加到根目录 由Scrapy创建的处理程序，这是一种笨拙的方式 过滤项目不同部分的所有记录器 （中间件、蜘蛛等）：

```
import logging
import scrapy

class MySpider(scrapy.Spider):
    # ...
    def __init__(self, *args, **kwargs):
        for handler in logging.root.handlers:
            handler.addFilter(ContentFilter())
```

或者，您可以选择特定的记录器 并在不影响其他记录器的情况下隐藏它：

```
import logging
import scrapy

class MySpider(scrapy.Spider):
    # ...
    def __init__(self, *args, **kwargs):
        logger = logging.getLogger('my_logger')
        logger.addFilter(ContentFilter())
```

## scrapy.utils.log module[¶](https://docs.scrapy.org/en/latest/topics/logging.html#module-scrapy.utils.log "Permalink to this heading")

Scrapy.utils.log.configure_logging（设置=无，install_root_handler=真**)**[[来源]](https://docs.scrapy.org/en/latest/_modules/scrapy/utils/log.html#configure_logging)[¶](https://docs.scrapy.org/en/latest/topics/logging.html#scrapy.utils.log.configure_logging "Permalink to this definition")初始化 Scrapy 的日志记录默认值。

参数* 设置 （dict、设置对象或） – 用于创建和配置处理程序的设置 根记录器（默认值：无）。`<span class="pre">None</span>`

* **install_root_handler** （[*bool*](https://docs.python.org/3/library/functions.html#bool "(in Python v3.11)")） – 是否安装根日志记录处理程序 （默认值：真）

此函数执行以下操作：

* 通过 Python 标准日志记录路由警告和扭曲日志记录
* 将调试和错误级别分别分配给刮板和扭曲记录器
* 如果设置为 True LOG_STDOUT则路由标准输出以记录

当为 True（默认值）时，此函数也 根据给定的设置为根记录器创建处理程序 （请参阅日志记录设置）。您可以覆盖默认选项 使用参数。当为空或无时，默认值 被使用。`<span class="pre">install_root_handler</span>``<span class="pre">settings</span>``<span class="pre">settings</span>`

`<span class="pre">configure_logging</span>`在使用 Scrapy 命令时自动调用 或爬网程序进程，但需要显式调用 使用爬虫运行器运行自定义脚本时。 在这种情况下，不需要使用它，但建议使用。

运行自定义脚本时的另一个选项是手动配置日志记录。 为此，您可以使用[`<span class="pre" _istranslated="1">logging.basicConfig（）</span>`](https://docs.python.org/3/library/logging.html#logging.basicConfig "(in Python v3.11)")来设置基本的根处理程序。

请注意，爬网程序进程会自动调用 ， 所以建议只将logging.basicConfig（）与CrawlerRunner一起使用。`<span class="pre">configure_logging</span>`

以下是有关如何将或更高消息重定向到文件的示例：`<span class="pre">INFO</span>`

```
import logging

logging.basicConfig(
    filename='log.txt',
    format='%(levelname)s: %(message)s',
    level=logging.INFO
)
```

请参阅[从脚本运行](https://docs.scrapy.org/en/latest/topics/practices.html#run-from-script) Scrapy 以获取有关使用 Scrapy 的更多详细信息 道路。


# Scrapy中间件

# Scrapy常见问题
### Scrapy之Request函数回调未执行解决方案


scrapy 执行Request函数时，回调函数未执行情况：

```
yield scrapy.Request(url=parse.urljoin(response.url, post_url), headers=self.headers, callback=self.parse_detail)
```

执行的时候发现parse_detail未被调用，很大可能是被allowed_domains给过滤掉了。查看scrapy的运行日志，可以查看 **'offsite/filtered': 21** ,被过滤了21个域名。

其实，这些日志信息都是由 scrapy 中的一个 middleware 抛出的，如果没有自定义，那么这个 middleware 就是默认的 `Offsite Spider Middleware`，它的目的就是过滤掉那些不在 `allowed_domains` 列表中的请求 requests。

再次查看手册中关于 `OffsiteMiddleware` 的部分([https://doc.scrapy.org/en/latest/topics/spider-middleware.html#scrapy.spidermiddlewares.offsite.OffsiteMiddleware](https://doc.scrapy.org/en/latest/topics/spider-middleware.html#scrapy.spidermiddlewares.offsite.OffsiteMiddleware))

这些日志信息都是由 [scrapy](https://so.csdn.net/so/search?q=scrapy&spm=1001.2101.3001.7020) 中的一个 middleware 抛出的，如果没有自定义，那么这个 middleware 就是默认的 `Offsite Spider Middleware`，它的目的就是过滤掉那些不在 `allowed_domains` 列表中的请求 requests。

再次查看手册中关于 `OffsiteMiddleware` 的部分([https://doc.scrapy.org/en/latest/topics/spider-middleware.html#scrapy.spidermiddlewares.offsite.OffsiteMiddleware](https://doc.scrapy.org/en/latest/topics/spider-middleware.html#scrapy.spidermiddlewares.offsite.OffsiteMiddleware))

解决方案：

两种方法能够使 requests 不被过滤:

1. 在 `allowed_domains` 中加入 url ；
2. 在 scrapy.Request() 函数中将参数 `dont_filter=True` 设置为 True。

### 一个Scrapy项目下的多个爬虫如何同时运行
#### 串行执行
新建run.py:
```
import os
from scrapy import cmdline
os.system("scrapy crawl ceshi_spider1")
cmdline.execute("scrapy crawl ceshi_spider2".split())
```
或者:
```
from scrapy import cmdline
from scrapy.cmdline import execute
import sys,time,os

#会全部执行爬虫程序
os.system('scrapy crawl ccdi')
os.system('scrapy crawl ccxi')
```
或者:
```
import subprocess
 
def crawl_work():
    subprocess.Popen('scrapy crawl yourspidername_1').wait()
    subprocess.Popen('scrapy crawl yourspidername_2').wait()
 
 
if __name__=='__main__':
    crawl_work()
```

利用 os.system来运行爬虫文件，这样写当 ceshi_spider1 运行完了，接着就会运行 ceshi_spider2爬虫文件。
此时a爬虫执行完毕会执行b爬虫
#### 并行执行
回到我们的例子中，修改 新建run.py代码为：

```
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

settings = get_project_settings()
process = CrawlerProcess(settings)
process.crawl('ceshi_spider1')
process.crawl('ceshi_spider2')
process.start()
```
### 运行爬虫文件的时候传参

```
import os

citys = {
    "仲恺区": "441392",
    "惠城区": "441302",
    "惠阳区": "441303",
}
for city, city_code in citys.items():
    os.system(f'scrapy crawl huicheng_spider -a region={city} -a idx={city_code}')
123456789
```

=-a=可以自定义传参，当我们运行这个启动文件的时候参数在爬虫的整个生命周期都是存在的。

```
class CeshiSpiderSpider(scrapy.Spider):
    name = 'ceshi_spider'

    def __init__(self, region, index):
        self.region = region
        self.index = index
```

# 数据统计与收集

虽然大多数其他抓取库和框架只专注于发出请求和解析响应，但 Scrapy 有一个完整的日志记录和统计层，可以实时跟踪您的蜘蛛。在开发蜘蛛时，测试和调试蜘蛛变得非常容易。

您可以轻松自定义日志记录级别，并使用几行代码将更多统计信息添加到爬虫中的默认 Scrapy 统计信息中。

仅依靠使用这种方法来监控刮板的主要问题是，它在生产中很快就会变得不切实际且繁琐。特别是当您每天在多个服务器上运行多个蜘蛛时。


您可以使用在运行结束时运行的统计信息收集器。

将其添加到settings.py：

```javascript
STATS_CLASS = 'mycrawler.MyStatsCollector.MyStatsCollector'
```

复制

下面是一个将MyStatsCollector.py输出到文件的基本实现：

```javascript
from scrapy.statscollectors import StatsCollector
from scrapy.utils.serialize import ScrapyJSONEncoder

class MyStatsCollector(StatsCollector):
    def _persist_stats(self, stats, spider):
        encoder = ScrapyJSONEncoder()
        with open("stats.json", "w") as file:
            data = encoder.encode(stats)
            file.write(data)
```

### 方式二
我的代码在下面，是文件的一部分。这应该为你如何实现自我提供指导。middleware.py
```
# -*- coding: utf-8 -*-

# Define here the models for your spider middleware

from scrapy import signals
import datetime
from sqlalchemy.orm import sessionmaker
from <botname>.models import Jobs, db_connect

class SaveJobInDatabase(object):

    @classmethod
    def from_crawler(cls, crawler):
        s = cls(crawler)
        crawler.signals.connect(s.spider_closed, signal=signals.spider_closed)
        return s

    def spider_closed(self, spider, reason):
        db_arg = getattr(spider,'addtodatabase','true')
        stats = spider.crawler.stats.get_stats()

        job = {}
        job['job_id'] = self.get_jobid()
        job['start_timestamp'] = stats.get('start_time').strftime('%Y-%m-%d %H:%M:%S')
        job['end_timestamp'] = stats.get('finish_time').strftime('%Y-%m-%d %H:%M:%S')
        job['spider_name'] = spider.name
        job['items_scraped'] = stats.get('item_scraped_count')
        job['items_dropped'] = stats.get('item_dropped_count')
        job['finish_reason'] = stats.get('finish_reason')

        """
        Save jobs in the database.
        This method is called whenever the spider is finished (closed)
        """
        session = self.Session()
        job_add = Jobs(**job)
        session.add(job_add)
        session.commit()
```
并确保更新并添加类：settings.py
```
SPIDER_MIDDLEWARES = {
    'botname.middlewares.SaveJobInDatabase': 300,
}
```

### 数据统计收集
Scrapy提供了方便的收集数据的机制。数据以key/value方式存储，值大多是计数值。 该机制叫做数据收集器(Stats Collector)，可以通过 Crawler API 的属性 stats 来使用
无论数据收集(stats collection)开启或者关闭，数据收集器永远都是可用的。 因此您可以import进自己的模块并使用其API(增加值或者设置新的状态键(stat keys))。 该做法是为了简化数据收集的方法: 您不应该使用超过一行代码来收集您的spider，Scrpay扩展或任何您使用数据收集器代码里头的状态。

数据收集器的另一个特性是(在启用状态下)很高效，(在关闭情况下)非常高效(几乎察觉不到)。

数据收集器对每个spider保持一个状态表。当spider启动时，该表自动打开，当spider关闭时，自动关闭。

**数据收集各种函数**

**stats.set_value('数据名称', 数据值)设置数据**
**stats.inc_value('数据名称')增加数据值，自增1**
**stats.max_value('数据名称', value)当新的值比原来的值大时设置数据**
**stats.min_value('数据名称', value)当新的值比原来的值小时设置数据**
**stats.get_value('数据名称')获取数据值**
**stats.get_stats()获取所有数据**

**举例：**



# -*- coding: utf-8 -*-
 
import scrapy
 
from scrapy.http import Request,FormRequest
 
class PachSpider(scrapy.Spider):                            #定义爬虫类，必须继承scrapy.Spider
 
    name = 'pach'                                           #设置爬虫名称
 
    allowed_domains = ['www.dict.cn']                       #爬取域名
 
    def start_requests(self):    #起始url函数，会替换start_urls
 
        return [Request(
 
            url='http://www.dict.cn/9999998888',
 
            callback=self.parse
 
        )]
 
    # 利用数据收集器，收集所有404的url以及，404页面数量
 
    handle_httpstatus_list = [404]                                  # 设置不过滤404
 
    def __init__(self):
 
        self.fail_urls = []                                         # 创建一个变量来储存404URL
 
    def parse(self, response):                                      # 回调函数
 
        if response.status == 404:                                  # 判断返回状态码如果是404
 
            self.fail_urls.append(response.url)                     # 将URL追加到列表
 
            self.crawler.stats.inc_value('failed_url')              # 设置一个数据收集，值为自增，每执行一次自增1
 
            print(self.fail_urls)                                   # 打印404URL列表
 
            print(self.crawler.stats.get_value('failed_url'))       # 打印数据收集值
 
        else:
 
            title = response.css('title::text').extract()
 
            print(title)
```






# 参考资料
[爬虫框架 Scrapy 详解](https://blog.csdn.net/m0_67403076/article/details/126081516)
[Scrapy教程](https://www.imooc.com/wiki/scrapylesson)
[Scrapy官方](https://scrapy-chs.readthedocs.io/zh_CN/0.24/)
[scrapy日志系统](https://blog.csdn.net/Qwertyuiop2016/article/details/109773008)
[Python中Scrapy框架的代理使用](https://blog.csdn.net/CorGi_8456/article/details/125737024)
[Python : Xpath简介及实例讲解](https://blog.csdn.net/xiaobai729/article/details/124079260)
[Python中Scrapy框架](https://blog.csdn.net/qq_62789540/article/details/124193329)
[日志](https://docs.scrapy.org/en/latest/topics/logging.html)


[给scrapy插上新功能--增加发邮件提醒](https://zhuanlan.zhihu.com/p/342877367)
[第六章 第三节 数据统计和邮件发送](https://zhuanlan.zhihu.com/p/98728261)