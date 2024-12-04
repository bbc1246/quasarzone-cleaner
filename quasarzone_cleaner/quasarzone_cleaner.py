import json
import os

from requests.exceptions import ConnectTimeout
from requests.exceptions import ProxyError
from twocaptcha import TwoCaptcha
from bs4 import BeautifulSoup
from typing import Union
import requests
import urllib.parse
import urllib3
import time
import re

import quasarzone_cleaner.quasarzone_cleaner

MAX_DELAY = 0.9

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class Cleaner:
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.66 Safari/537.36'
    login_headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.quasarzone.com/",
        'User-Agent': user_agent
    }

    delete_headers = {
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'ko-KR,ko;q=0.9',
        'Connection': 'keep-alive',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Host': 'q.com',
        'Origin': 'https://quasarzone.com',
        'Referer': '',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': user_agent
    }


    def __init__(self):
        self.session = requests.Session()
        self.data_id = ''
        self.token =''
        self.session.verify = False
        self.session.headers.update({'User-Agent': self.user_agent})
        self.post_list = []
        self.proxy_list = []
        self.twocaptcha_key = ''
        self.solver : TwoCaptcha
        self.delay = MAX_DELAY
        self.nick =''

    def updateDelay(self):
        self.delay = round(MAX_DELAY / (len(self.proxy_list) or 1), 1)

    def _handleProxyError(func):
        def wrapper(self, *args):
            result = None
            while True:
                try:
                    result = func(self, *args)
                except (ProxyError, ConnectTimeout):
                    self.proxy_list.pop()
                    self.updateDelay()
                else:
                    return result

        return wrapper

    def serializeForm(self, input_elements):
        form = {}
        for element in input_elements:
            form[element['name']] = element['value']
        return form

    def getUserId(self) -> str:
        return self.user_id

    def setUserId(self, user_id: str) -> None:
        self.user_id = user_id

    def setProxyList(self, proxy_list: list) -> None:
        self.proxy_list = proxy_list
        self.updateDelay()

    def set2CaptchaKey(self, key) -> bool:
        twocaptcha_url = f'https://2captcha.com/in.php?key={key}'

        res = requests.get(twocaptcha_url)

        if res.text in ('ERROR_KEY_DOES_NOT_EXIST', 'ERROR_WRONG_USER_KEY'):
            return False
        
        self.twocaptcha_key = key

        self.solver = TwoCaptcha(key)
        
        return True

    def getCookies(self) -> dict:
        return self.session.cookies.get_dict()


    def getUserInfo(self,cookies) -> dict:
        self.session.headers.update(self.login_headers)

        for cookie in cookies:
            # Selenium 쿠키에서 필요한 정보만 추출하여 requests 쿠키 형식으로 변환
            self.session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])

        res = self.session.get('https://quasarzone.com')

        soup = BeautifulSoup(res.text, 'html.parser')
        self.token = soup.find("meta", {'name': 'csrf-token'})['content']
        url_match = re.search(r"if\(type === 'post'\)\s*{\s*openWindow\('([^']+)'", res.text)
        self.data_id =  url_match.group(1) if url_match else ''
        match = re.search(r'/board/([A-Za-z0-9.-]+)/', self.data_id)
        self.user_id =  match.group(1) if match else ''

        nickname = soup.select_one('span[data-nick]')['data-nick']

        article_num =  re.search(r'var postCount = "(\d+)"', res.text).group(1)

        comment_num =  re.search(r'var commentCount = "(\d+)"', res.text).group(1)

        remove_bracket = lambda x: x[1:-1]

        return {
            'nickname': nickname,
            'article_num': article_num,
            'comment_num': comment_num,
        }


    def aggregatePosts(self, gno: str, post_type: str, signal,count) -> None:
        try:
            self.session.headers.update({'User-Agent': self.user_agent})
            proxies = self.getProxy()
            match = re.search(r'/bbs/([^/]+)', gno)
            bbsurl = match.group(0)
            boardname = match.group(0)[5:]


        except Exception as e:
            signal.emit({'type': 'logs', 'data': str(e)})
            return

        try:
            result = self.session.get(gno, proxies=proxies)
            self.nick = BeautifulSoup(result.text, 'html.parser').find('p', {'class': 'nick'}).text[:-2]
        except Exception as e:
            signal.emit({'type': 'logs', 'data': gno + str(e)})
            return

        if post_type == 'posting':
            nextpage = 1
            while True:
                search = f'{gno}?_method=post&type=&page={nextpage}&kind=nick&keyword={urllib.parse.quote_plus(self.nick)}'
                pages = self.session.get(search,proxies=proxies)
                if pages.text.find(bbsurl) == -1:
                    time.sleep(self.delay*3)
                    continue
                soup = BeautifulSoup(pages.text,'html.parser')

                dabate_div = soup.find('div', class_=['dabate-type-list', 'market-type-list market-info-type-list relative'])
                if dabate_div == None:
                    links = [p.find_parent('a') for p in soup.find_all('p', class_=['title subject-link', 'tit subject-link']) if p.find_parent('a')]
                else:
                    links = dabate_div.find_all('a', class_='subject-link')
                if len(links) == 0:
                    break

                for link in links:
                    writeno = re.search(r'/views/(\d+)', link['href'])
                    if writeno:
                        number = writeno.group(1)  # 숫자 부분만 추출
                        payload = {'_token': self.token, '_method': 'put', 'type': 'update', 'writeId': number,
                                   'html': 'html1',
                                   'subject': '삭제', 'content': '삭제'}
                        updateurl = f'{gno}/update/{number}'
                        res = self.session.post(updateurl, payload,proxies=proxies)
                        if res.status_code == 200:
                            signal.emit( {'type': 'page_update', 'max': count , 'cur': 1 })
                        time.sleep(self.delay)

                nextpage+=1


        elif post_type == 'comment':
            nextpage = 1
            while True:
                search = f'{gno}?page={nextpage}'
                pages = self.session.get(search, proxies=self.getProxy())
                if pages.text.find(bbsurl) == -1:
                    time.sleep(self.delay * 3)
                    continue

                signal.emit({'type': 'logs', 'data': search})

                soup = BeautifulSoup(pages.text, 'html.parser')

                dabate_div = soup.find('div', class_=['dabate-type-list', 'market-type-list market-info-type-list relative'])

                if dabate_div:
                    # 'dabate_div' 내에서 'subject-link' 클래스를 가진 모든 <a> 태그 찾기
                    links = dabate_div.find_all('a', class_='subject-link')
                else:
                    # 'dabate_div'이 없을 경우 'title subject-link' 또는 'tit subject-link'를 가진 모든 <p> 태그에서 부모 <a> 태그 찾기
                    links = [
                        p.find_parent('a') for p in soup.find_all('p', class_=['title subject-link', 'tit subject-link']) if p.find_parent('a')
                    ]

                # 결과가 없으면 빈 리스트로 초기화
                links = links or []
                lensubjects = len(links)
                if links == None or lensubjects == 0:
                    break

                links = []
                for span in soup.find_all("span", class_="ctn-count my-active"):
                    # 시블링에서 a 태그의 href 속성 값 가져오기
                    sibling_link = span.find_previous("a")
                    if sibling_link:
                        links.append(sibling_link.get("href"))

                for link in links:
                    writeno = re.search(r'/views/(\d+)', link)
                    if writeno:
                        firstpage = 1
                        number = writeno.group(1)  # 숫자 부분만 추출
                        commenturl = f'https://quasarzone.com/comments/{boardname}/getComment?boardName={boardname}&writeId={number}&page={firstpage}'
                        res = self.session.get(commenturl,proxies=self.getProxy())
                        value = json.loads(res.text)

                        while True:
                            match_ids = []
                            if len(value['comm_list']) > 0:
                                for item in value['comm_list']['comments']['data']:
                                    if item.get('user_id') == self.user_id:
                                        match_ids.append(item.get('id'))
                                for coid in match_ids:
                                    payload = {'_token': self.token, '_method': 'put',  'writeId': number,'commentId' : coid ,'commentSort' : 'old' ,'requestUri' :f'{bbsurl}/views/'+number+'?'+str(firstpage) ,'page' : firstpage, 'content': '삭제'}
                                    updateurl = f'{gno}/comments/update'
                                    res = self.session.post(updateurl, payload,proxies=self.getProxy())
                                    signal.emit({'type': 'page_update', 'max': count, 'cur': 1})
                                    time.sleep(self.delay)
                            elif len(value['comm_list']) == 0:
                                break
                            if value['comm_list']['comments']['next_page_url'] == None:
                                break
                            firstpage+=1
                            commenturl = f'https://quasarzone.com/comments/{boardname}/getComment?boardName={boardname}&writeId={number}&page={firstpage}'
                            res = self.session.get(commenturl, proxies=self.getProxy())
                            value = json.loads(res.text)

                nextpage+=1

    def getBoardCount(self, url)  -> Union[dict, str]:
        self.session.headers.update({'User-Agent': self.user_agent})
        res= self.session.get(url,proxies=self.getProxy())
        soup = BeautifulSoup(res.text, 'html.parser')

        script_tag = soup.find('script', text=re.compile(r'var\s+board\s*=\s*{'))
        if script_tag:
            # JavaScript 코드에서 JSON 부분 추출
            match = re.search(r'var\s+board\s*=\s*({.*?});', script_tag.string, re.DOTALL)
            if match:
                board_json_str = match.group(1)

                # JSON 문자열 파싱
                board_data = json.loads(board_json_str)
                wirtecount = board_data['count_write']
                commentcount = board_data['count_comment']
                boardname = board_data['subject']
                if wirtecount < 0:
                    wirtecount = 0
                if commentcount <0:
                    commentcount =0
                return {'writecount' : wirtecount , 'commentcount':commentcount}
            else:
                print ("board JSON을 찾을 수 없습니다.")
                return {'writecount' : 0 , 'commentcount':0}
        else:
            print ("<script> 태그에서 'var board'를 찾을 수 없습니다.")
            return {'writecount' : 0 , 'commentcount':0}
        return {'writecount' : 0 , 'commentcount':0}

    @_handleProxyError
    def getBoardList(self, post_type: str) -> Union[dict, str]:

        if self.data_id != '':
            self.session.headers.update({'User-Agent': self.user_agent})
            res= self.session.get('https://quasarzone.com',proxies=self.getProxy())
            soup = BeautifulSoup(res.text, 'html.parser')
            # boardlist = [a["href"] for a in soup.select("div.menu a")]
            boardlist = [(a["href"], a.text.strip()) for a in soup.select("div.menu a")]

            return boardlist

    def getQuicklist(self, post_type: str) -> Union[dict, str]:
            self.session.headers.update({'User-Agent': self.user_agent})
            res= self.session.get(self.data_id,proxies=self.getProxy())
            soup = BeautifulSoup(res.text, 'html.parser')
            links = soup.find_all("a", href=True)

            # 정규 표현식을 이용해 각 링크의 인수 추출
            gall_list_elements = []
            for link in links:
                href = link["href"]
                match = re.search(r"moveBoardPage\('([^']*)', '([^']*)', '([^']*)', '([^']*)'\)", href)
                if match:
                    args = match.groups()
                    gall_list_elements.append(args)

            # 결과 출력
            for i, args in enumerate(gall_list_elements, 1):
                print(f"Link {i} arguments:", args)
            # 1.게시판명 2.게시글번호 3. 4.댓글번호
            #https://quasarzone.com/bbs/qb_free/views/1

            gall_list = {}
            for gall_list_element in gall_list_elements:
                gno = gall_list_element[1]
                gname = gall_list_element[0]
                gcnt = gall_list_element[2]
                gcono = gall_list_element[3]
                gall_list[gno] =(gno,gname,gcnt,gcono)
            return gall_list

    def getProxy(self) -> dict:
        if self.proxy_list:
            proxy = self.proxy_list.pop(0)
            self.proxy_list.append(proxy)
            return {
                'http': proxy,
                'https': proxy
            }

        return {}
    
    def solveCaptcha(self, page_url) -> str:
        result = self.solver.recaptcha(sitekey=self.dcinside_site_key, url=page_url)
        return result['code']
