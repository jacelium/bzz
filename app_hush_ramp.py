import json, os, sys, re, time, datetime, random
from websockets.sync.client import connect
from ..bzz import Bzz


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

  matches = re.search('[bB][zZ]{1,3}', post)

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

baseline = 10
last_intensity = baseline # The last intensity value set; used internally
secs = 20 # How long a given intensity will last
decay_time = 5
end_time = datetime.datetime.now() # Precomputed end of the current secs-length window
baseline = 10
reduction = 5

statsfile = './stats.json'
stats = {}
with open(statsfile, 'r') as f:
  stats = json.loads(f.read())

max_intensity = stats['max_intensity']
max_intensity_participants = set(stats['max_intensity_participants'])

max_run = stats['max_run']
max_run_participants = set(stats['max_run_participants'])

current_run = 0
current_run_participants = set()

def act(item, target_id, config):
  """ Acts on the output from Parse.
      Sets an intensity and holds there for a configurable about of time
      If new intensities come in, sets them at the end of that time.
  """
  global ws
  global end_time
  global last_intensity, max_intensity, max_intensity_participants
  global max_run, current_run, max_run_participants, current_run_participants

  now = datetime.datetime.now()
  if end_time < now:
    end_time = now

  intensity, user, sent = item

  delta = datetime.timedelta(0, secs if user is not None else decay_time)
  end_time = end_time + delta
  print(f'User is {user}; added {secs}s. Time is now {end_time} ({(end_time - now).total_seconds()}s)')

  if user is not None:
    with open(config.logfilepath, 'a+') as logfile:
      logfile.write(f'{target_id},{sent.isoformat()},{datetime.datetime.now().isoformat()},{intensity},{user}\n')
    current_run_participants.add(user)

  print(
    f'Modifying intensity {last_intensity} by {intensity} ({intensity/100}) ' + 
    f'on behalf of {user if user is not None else "host"}.'
  )

  if scaler != 1:
    intensity = (intensity/100) * scaler
    print(f'Scaled trigger: {intensity * 100}')

  last_intensity += intensity
  if last_intensity > 100:
    last_intensity = 100

  if last_intensity <= baseline:
    print(f'Intensity is at baseline ({baseline}); ending run of {current_run}s by {format_userlist(list(current_run_participants))}')
    last_intensity = baseline
    current_run = 0
    current_run_participants = set()
  else:
    print(f'Adding {secs if user is not None else decay_time} to current run')
    current_run += secs if user is not None else decay_time

  if current_run > max_run:
    print(f'New max run! {current_run} {current_run_participants}')
    max_run_participants = current_run_participants.copy()
    max_run = current_run

  if last_intensity > max_intensity and last_intensity > baseline:
    print(f'New max intensity! {last_intensity} by {user}')

    max_intensity = last_intensity
    max_intensity_participants = set([user])
  elif last_intensity == max_intensity:
    print(f'Matched max intensity! {last_intensity} by {user}')

    max_intensity_participants.add(user)

  with open(statsfile, 'w') as f:
    f.write(json.dumps({
      'max_intensity': max_intensity,
      'max_intensity_participants': list(max_intensity_participants),
      'max_run': max_run,
      'max_run_participants': list(max_run_participants),
    }))

  while True:
    try:
      ws.send(json.dumps(([{"ScalarCmd":{
        "Id":4,
        "DeviceIndex":0,
        "Scalars":[{"Index":0,"Scalar":last_intensity/100,"ActuatorType":"Vibrate"}]
      }}])))
      ws.recv()
      break
    except Exception as e:
      print('Connecting!')
      ws = connect("ws://localhost:12345")
      ws.send(json.dumps([{"RequestServerInfo":{"Id":1,"ClientName":"Bzz","MessageVersion":3}}]))
      ws.recv()

##################################################################
# New feature - we can pass an 'empty' function that receives the queue if empty
# and manipulates it. If this function returns True the results will be
# immediately evaluated rather than waiting a normal act cycle
##################################################################

def empty(queue):
  if datetime.datetime.now() > end_time and last_intensity > baseline:
    queue.append([-reduction, None, None])
    return True

# Stats

def format_userlist(input_list, sep=', ', last_sep=' and '):
  """ Takes a list and outputs it in the format:
      Item1, Item2, Item3 and Item4
  """

  output = sep.join(input_list)
  if sep in output:
    output = last_sep.join(output.rsplit(sep, 1))
  return output

def generate_stats(post_id, config):
  """ Reads stored stat items and generates output based on them.
      Returns a string that will be appended to the closed post. 
  """

  with open(statsfile, 'r') as f:
    stats = json.loads(f.read())

  return f"""

Closed at {datetime.datetime.strftime(datetime.datetime.now(), '%H:%M, %b %d')}

- Max intensity was {stats['max_intensity']} (from @{format_userlist(stats['max_intensity_participants'], ', @', ' and @')})
- Longest run was {stats['max_run']} seconds, well done @{format_userlist(stats['max_run_participants'], ', @', ' and @')}!
"""

##################################################################
# Start monitoring. Pass our two methods to the harness, along with our saved last_action_id if we have one.
##################################################################

print(f'Scaler is {scaler}')

bzz = Bzz(parse, act, config_file='config-hush-ramp.json', empty_function=empty, stats_function=generate_stats)

arg = sys.argv[1] if len(sys.argv) > 1 else ''

if arg == 'closepost':
  bzz.close_post()
  exit()
elif arg == 'newpost':
  bzz.create_post()
else:
  bzz.attach_to_post()

bzz.run()
