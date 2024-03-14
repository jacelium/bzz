import json, os, sys, re, time, datetime, random
from websockets.sync.client import connect
from bzz import Bzz


# All triggers will be scaled by this amount. e.g. to half all triggers, set this to 0.5 or 1/2
scaler = 1

##################################################################
# We need to provide two methods. The first, Parse, takes
# a post and extracts some information from it, then returns
# an array of that information to be queued and carried out
# by Act.
# If we're skipping, return False instead.
# This method is passed the status_dict of the current post
# and the config object for the instance.
##################################################################

def parse(item, config):
  """ Checks if a post matches a regex. If so, calculates
      intensity based on the length of the match and pushes:
      [intensity, source account, created datetime]
      If disallowed by allow or deny list, returns False
  """

  post = item['content']

  matches = re.search('[bB][z]{1,10}', post)

  if matches:
    count = len(matches.group(0))-1
    intensity = count * 10
    acct = item['account']['acct']
    if config.deny_list is not None and acct.lower() in config.deny_list:
       print(f'Skipping {intensity} from {acct}, sent {item["created_at"].isoformat()} [denylist]')
    elif config.allow_list is not None and acct.lower() not in config.allow_list:
       print(f'Skipping {intensity} from {acct}, sent {item["created_at"].isoformat()} [allowlist]')
    else:
       print(f'Pushing {intensity} from {acct}, sent {item["created_at"].isoformat()}')
       return([intensity, acct, item['created_at']])
  return False

##################################################################
# The second is what to actually do with what Parse produces.
##################################################################

# We realistically need  to do actual setup on this before it's easily usable. For now
# we just assume that intiface knows about our toy and it's the only one being reported
# so we know it's deviceindex 0.

# Intiface is running on my local machine; I'm SSHing to my remote server where Bzz is
# running, and using an SSH tunnel to forward requests on that end to port 12345 to my
# local port 12345 where Intiface can see it.

ws = connect("ws://localhost:12345")
ws.send(json.dumps([{"RequestServerInfo":{"Id":1,"ClientName":"Bzz","MessageVersion":3}}]))

last_intensity = 0 # The last intensity value set; used internally
secs = 10 # How long a given intensity will last
end_time = datetime.datetime.now() # Precomputed end of the current secs-length window

def act(item, target_id, config):
  """ Acts on the output from Parse.
      Sets an intensity and holds there for a configurable about of time
      If new intensities come in, sets them at the end of that time.
  """
  global end_time
  global last_intensity

  now = datetime.datetime.now()
  if now < end_time:
    return False

  end_time = now + datetime.timedelta(0, secs)

  intensity, user, sent = item

  if user is not None:
    with open(config.logfilepath, 'a+') as logfile:
      logfile.write(f'{target_id},{sent.isoformat()},{datetime.datetime.now().isoformat()},{intensity},{user}\n')

  print(f'Setting {intensity} ({intensity/100}) on behalf of {user if user is not None else "host"}')

  last_intensity = intensity

  if scaler != 1:
    intensity = (intensity/100) * scaler
    print(f'Scaled trigger: {intensity * 100}')

  if intensity == 0:
    ws.send(json.dumps([{"StopDeviceCmd":{"Id":5,"DeviceIndex":0}}]))
    print(ws.recv())
  else:
    ws.send(json.dumps(([{"ScalarCmd":{
      "Id":4,
      "DeviceIndex":0,
      "Scalars":[{"Index":0,"Scalar":intensity/100,"ActuatorType":"Vibrate"}]
    }}])))
    print(ws.recv())

##################################################################
# New feature - we can pass an 'empty' function that receives the queue if empty
# and manipulates it. If this function returns True the results will be
# immediately evaluated rather than waiting a normal act cycle
##################################################################

# Reset intensity back to 0 if we haven't had anything
def empty(queue):
  if datetime.datetime.now() > end_time:
    if last_intensity > 0:
      queue.append([0, None, None])
      return True

##################################################################
# Start monitoring. Pass our two methods to the harness, along with our saved last_action_id if we have one.
##################################################################

print(f'Scaler is {scaler}')

bzz = Bzz(parse, act, config_file='config-hush.json', empty_function=empty)

arg = sys.argv[1] if len(sys.argv) > 1 else ''

if arg == 'closepost':
  bzz.close_post()
  exit()
elif arg == 'newpost':
  bzz.create_post()
else:
  bzz.attach_to_post()

bzz.run()
