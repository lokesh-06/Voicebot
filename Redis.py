import redis
import json
from datetime import datetime
import pytz

class Cache:
	def __init__(self):
		self.r = redis.Redis(host='localhost', port='6379')


	def clear_redis_by_time(self, key):
		ist = pytz.timezone('Asia/Kolkata')
		current_date = datetime.now(ist).date()
		current_data_redis = eval(self.r.get(key).decode())
		dicti = current_data_redis.copy()
		for num in current_data_redis:
			redis_date = current_data_redis[num]['time_range']
			date_, time_ = redis_date.split("|")
			foo = datetime.strptime(date_, '%d/%m/%Y').date()
			if foo < current_date:
				del dicti[num]
		self.r.set(key, dicti)
  
	def set(self, key, value):
		self.r.set(key, str(value))

	def get(self, key):
		value = self.r.get(key)
		if value:
			try:
				#print(value)
				return eval(value.decode('utf-8'))
			except NameError as e:
				#raise e
			  return eval(value.decode())

	def delete(self, key):
		self.r.delete(key)

	def create_dict(self, name, payload):
		for key, value in payload.items():
			self.r.hset(name, key, value)

	def get_dict(self, name):
		x = self.r.hgetall(name)
		if x:
			return {k.decode('utf-8'): v.decode('utf-8') for k, v in self.r.hgetall(name).items()}

	def set_item(self, name, key, value):
		self.r.hset(name, key, value)

	def get_item(self, name, key):
		x = self.r.hget(name, key)
		if x:
			return x.decode('utf-8')

	def delete_item(self, name, key):
		self.r.hdel(name, key)

	def delete_all(self):
		self.r.flushdb()

	def get_all(self):
		return self.r.keys()
