import re
import urllib.request
import urllib.parse
import http.cookiejar
import bs4
import random

from urllib.parse import urlencode
from credentials import credentials

class MultipartMimeFormData(object):
    def __init__(self):
        self.parts = []
        self.boundary = "----------------MultipartMimeFormDataBoundary%d" % random.randrange(1000000000)
    def get_content_type(self):
        return 'multipart/form-data; boundary=%s' % self.boundary
    def add_field(self, name, value):
        part = 'Content-Disposition: form-data; name="%s"' % name
        part += "\r\n\r\n%s\r\n" % value
        self.parts.append(part)
    def add_csv_file(self, name, filename, csv_data):
        part = 'Content-Disposition: form-data; name="%s"; filename="%s"' % (name, filename)
        part += "\r\nContent-Type: text/csv"
        part += "\r\n\r\n%s\r\n" % csv_data
        self.parts.append(part)
    def __str__(self):
        return "--" + self.boundary + "\r\n" + ("--" + self.boundary + "\r\n").join(self.parts) + "--" + self.boundary + "--\r\n"

class DeckboxSession(object):
    LOGIN = "https://deckbox.org/accounts/login"
    EXPORT = "http://deckbox.org/sets/export/%(set)d?format=csv&s=%(set)d&o=&columns=&v2=true"
    USER = "http://deckbox.org/users/%(username)s"
    CLEAR = "http://deckbox.org/detailed_cards_sets/remove/"
    IMPORT = "http://deckbox.org/detailed_cards_sets/import_csv"

    def __init__(self, login=None, password=None, debug=False):
        jar = http.cookiejar.CookieJar()
        self.login = login
        self.password = password
        self.debug = debug
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.token = None
        self.referer = None
        self.logged_in = False

    def get_inventory_csv_export_for_username(self, username):
        return self.get_csv_export_for_set_id(self.get_user_inventory_set_id(username)).read().decode('utf-8')

    def update_inventory(self, csv):
        self.ensure_logged_in()
        self.clear_inventory()
        self.import_inventory(csv)

    def ensure_logged_in(self):
        if not self.logged_in:
            self.request_soup(self.LOGIN)
            soup = self.request_soup(self.LOGIN,
                                     login=self.login,
                                     password=self.password)
            self.inventory_set_id = self.find_user_inventory_set_id(soup)
            self.logged_in = True

    def clear_inventory(self):
        self.request_soup(self.CLEAR, set_id=self.inventory_set_id)

    def import_inventory(self, csv):
        soup = self.request_soup(self.IMPORT,
                                 file_field_name="import_csv_file",
                                 file_data=csv,
                                 just_check="false",
                                 set_id=str(self.inventory_set_id),
                                 check="true")
        if (soup.find(lambda tag: tag.name == "script" and tag.string and tag.string.count("Tcg.ui.flash.updateAndShow"))):
            print("Imported new inventory")
        else:
            print("Import might have failed")


    def get_csv_export_for_set_id(self, set_id):
        return self.opener.open(self.EXPORT % {"set": set_id})

    def get_user_inventory_set_id(self, username):
        soup = self.request_soup(self.USER % {"username": username})
        return self.find_user_inventory_set_id(soup)

    def find_user_inventory_set_id(self, soup):
        inventory_link = soup.find(lambda tag: tag.name == "a" and tag.string == "Inventory")
        return int(re.match('/sets/(\d+)', inventory_link["href"]).group(1))

    def request_soup(self, url, file_field_name=None, file_data=None, **fields):
        if self.debug:
            print("Requesting %s" % url)

        if len(fields) and self.token:
            fields["authenticity_token"] = self.token

        if file_field_name:
            request = self.get_file_data_request(url,
                                                 file_field_name=file_field_name,
                                                 file_data=file_data,
                                                 **fields)
            response = self.opener.open(request)
        elif len(fields):
            response = self.opener.open(url, urlencode(fields).encode('utf-8'))
        else:
            response = self.opener.open(url)

        if self.debug:
            print(response.info)

        soup = bs4.BeautifulSoup(response)
        if self.debug:
            print(soup.prettify())

        self.update_authenticity_token(soup)
        self.referer = response.geturl()
        return soup

    def get_file_data_request(self, url, file_field_name=None, file_data=None, **fields):
        msg = MultipartMimeFormData()
        msg.add_csv_file(file_field_name, "import.csv", file_data)
        for field, value in fields.items():
            msg.add_field(field, value)
            body = str(msg).encode('utf-8')
        request = urllib.request.Request(url)
        request.add_header("Content-Type", msg.get_content_type())
        request.add_header("Content-Length", len(body))
        request.add_header("Referer", self.referer)
        request.add_data(body)
        return request

    def update_authenticity_token(self, soup):
        token_script = soup.find(lambda tag: tag.name == "script" and tag.string and tag.string.count("_token = "))
        if (token_script):
            self.token = re.search('_token = "([^"]*)";', token_script.string).group(1)
        else:
            token_input = soup.find(lambda tag: tag.name == "input" and tag["name"] == "authenticity_token")
            if (token_input):
                self.token = token_input["value"]
