"""
Copyright © Divyanshu Kakwani 2019, all rights reserved

Defines general spiders for news sources

There are two general spiders: RecursiveSpider and SitemapSpider. The
former starts at the home page and recursively follows all the links. The
latter extracts all the urls from the sitemap and then simply pulls those urls
without following further links found in the page.

Custom spiders are needed to handle irregular news sources. A custom spider
should have a name in the format <Source Name>Spider. e.g. SahilonlineSpider
and it should inherit from one of the general spider and override whatever
functionality it wants to override

"""
import scrapy
import json
import os
import tldextract

from lxml.html.clean import Cleaner
from scrapy.linkextractors import LinkExtractor
from scrapy.selector import Selector
from datetime import datetime
from twisted.internet import task
from ..corpus import NewsCorpus
from ..language import code2script
from datetime import date, timedelta


class BaseNewsSpider(scrapy.Spider):

    name = 'base-news-spider'

    def __init__(self, *args, **kwargs):
        self.lang = kwargs['lang']
        self.script = code2script(self.lang)
        self.name = kwargs['source_name']
        self.html_path = kwargs['html_path']
        self.home_url = kwargs['home_url']
        self.log_path = kwargs['log_path']
        self.pages_crawled = 0
        self.recent_pgcnt = 0
        self.recent_pgcnts = [0, 0, 0, 0, 0, 0]
        self.cleaner = Cleaner(scripts=True, javascript=True, style=True,
                               comments=True, links=False, meta=False,
                               page_structure=False, embedded=True,
                               frames=True, forms=False, annoying_tags=False)

        os.makedirs(self.html_path, exist_ok=True)

        parts = tldextract.extract(self.home_url)
        domain = '{}.{}'.format(parts.domain, parts.suffix)

        if len(parts.subdomain) > 0:
            domain = '{}.{}'.format(parts.subdomain, domain)

        self.allowed_domains = [domain]

        self.html_corpus = NewsCorpus(self.lang, self.html_path)

        super().__init__(self.name)

        job_id = kwargs.get('_job', self.name)
        os.makedirs(os.path.join(self.log_path, 'stats'), exist_ok=True)
        self.log_file = os.path.join(self.log_path, 'stats', job_id)

        call = task.LoopingCall(self.log_stats)
        call.start(300)  # call every 5 mins

    def log_stats(self):
        del self.recent_pgcnts[0]
        self.recent_pgcnts.append(self.recent_pgcnt)
        self.recent_pgcnt = 0
        stats = {'lang': self.lang, 'source': self.name,
                 'pages_crawled': self.pages_crawled,
                 'recent_pgcnts': self.recent_pgcnts}
        with open(self.log_file, 'w') as fp:
            json.dump(stats, fp)

    def write_html(self, response):
        html = self.cleaner.clean_html(response.text)
        html_page = {
            'html': html,
            'source': self.name,
            'url': response.request.url,
            'timestamp': datetime.now().strftime('%d/%m/%y %H:%M')
        }
        self.html_corpus.add_instance(html_page)
        self.pages_crawled += 1
        self.recent_pgcnt += 1
        return html

    def parse(self, response):
        raise NotImplementedError

    def closed(self, reason):
        print('Closing spider. Name: ', self.name, ' Reason: ', reason)
        # self.store.upload(self.html_corpus, 'html')


class SitemapSpider(BaseNewsSpider, scrapy.spiders.SitemapSpider):

    name = 'sitemap-spider'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sitemap_urls = [kwargs['sitemap_url']]

    def parse(self, response):
        self.write_html(response)


class RecursiveSpider(BaseNewsSpider):

    name = 'recursive-spider'

    def __init__(self, *args, **kwargs):
        self.start_urls = [kwargs['home_url']]
        self.link_extractor = LinkExtractor()
        super().__init__(*args, **kwargs)

    def parse(self, response):
        self.write_html(response)

        links = self.link_extractor.extract_links(response)

        links = filter(lambda l: l.url.startswith(self.home_url), links)

        for link in links:
            yield scrapy.Request(link.url)


class SanjevaniSpider(RecursiveSpider):
    """
    Boilerpipe does not work for this news source
    """

    name = 'sanjevani-spider'

    def extract_article_content(self, html):
        sel = Selector(text=html)
        text = ''
        for node in sel.css('.entry-content *::text'):
            text = text + '\n' + node.extract()
        return text


class AnupambharatonlineSpider(RecursiveSpider):

    name = 'anupambharatonline'

    custom_settings = {
        'DUPEFILTER_CLASS': 'scrapy.dupefilters.BaseDupeFilter'
    }


class PanjuMagazineSpider(RecursiveSpider):

    name = 'panjumagazine'

    custom_settings = {
        'DUPEFILTER_CLASS': 'scrapy.dupefilters.BaseDupeFilter'
    }


class AjitjalandharSpider(RecursiveSpider):

    name = 'ajitjalandhar'

    def __init__(self, *args, **kwargs):
        self.start_urls = [kwargs['home_url']]
        start_date = date(2017, 1, 1)
        end_date = date(2020, 2, 29)
        delta = timedelta(days=1)
        while start_date <= end_date:
            url = start_date.strftime("http://beta.ajitjalandhar.com/edition/%Y%m%d.cms")
            self.start_urls.append(url)
            start_date += delta

        self.link_extractor = LinkExtractor()
        super().__init__(*args, **kwargs)


class NewsOnAirSpider(RecursiveSpider):
    name = "newsonair-spider"

    def __init__(self, *args, **kwargs):
        self.start_urls = [kwargs['home_url']]
        super().__init__(*args, **kwargs)
        if kwargs['lang'] == "en":
            exclude = [
                '/hindi/', '/Gujarati/', '/marathi/', '/urdu/', 
                '/tamil/', '/dogri/', '/Assamese/', '/Rajasthani/'
            ]
            self.link_extractor = LinkExtractor(deny=exclude)
        else:
            self.link_extractor = LinkExtractor()
