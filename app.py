#############################################################
# Shocker creds file should be a JSON file in this format:
#{
#  "shock_key": "The key from your share link (looks like a guid)",
#  "shock_username": "Your pishock username",
#  "shock_sharecode": "Your pishock sharecode",
#  "shock_appname": "The app name that will appear in Pishock logs"
#}
#############################################################

import json, os, sys, re, time, datetime, random
from pishockpy import PishockAPI
from bzz import Bzz

# All triggers will be scaled by this amount. e.g. to half all triggers, set this to 0.5 or 1/2
scaler = 1

# Utility functions

def format_userlist(input_list, sep=', ', last_sep=' and '):
  """ Takes a list and outputs it in the format:
      Item1, Item2, Item3 and Item4
  """

  output = sep.join(input_list)
  if sep in output:
    output = last_sep.join(output.rsplit(sep, 1))
  return output

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

creds = {}

with open('shock_creds.json', 'r') as creds_file:
  creds = json.loads(creds_file.read())

# we need a Pishock instance for this handler
ps = PishockAPI(creds['shock_key'], creds['shock_username'], creds['shock_sharecode'], creds['shock_appname'])

def act(item, target_id, config):
  """ Acts on the output from Parse.
      Sends a shock of the relevant intensity and logs some
      information for stats generation purposes. 
  """
  intensity, user, sent = item

  with open(config.logfilepath, 'a+') as logfile:
    logfile.write(f'{target_id},{sent.isoformat()},{datetime.datetime.now().isoformat()},{intensity},{user}\n')

  print(f'Sending {intensity} ({intensity/100}) on behalf of {user}')

  if scaler != 1:
    print(f'Scaled trigger: {(intensity/100) * scaler * 100}')

  ps.shock((intensity / 100) * scaler, 1)

##################################################################
# We can also optionally pass a stat generation method as a kwarg.
##################################################################

def generate_stats(post_id, config):
  """ Reads logged items and generates some stats based on them.
      Returns a string that will be appended to the closed post. 
  """

  known, updated = None, None

  with open(config.knownfilepath, 'r+') as knownfile:
    known = set(map(lambda x: x.strip(), knownfile.readlines()))
    updated = known.copy()

  logs = []
  with open(config.logfilepath, 'r') as logfile:
    logs = logfile.readlines()
  logs = list(filter(lambda x: x.startswith(str(post_id)), logs))

  count = len(logs)
  if count == 0:
    return '\n\nNo triggers received! :('

  newusers = set()
  max_intensity = 0
  total = 0
  biggest = set()

  for log in logs:
    fields = log.split(',')
    intensity, name = int(fields[3]), fields[4].strip()
    if name not in known:
      updated.add(name)
    if intensity >= max_intensity:
      max_intensity = intensity
      biggest.add(name)
    total += intensity

  biggest_count = 3
  biggest_names  = list(random.sample(biggest, min(biggest_count, len(biggest))))
  biggest_names = [f'@{x}' for x in biggest_names]
  if len(biggest) > biggest_count:
    biggest_names.append('others')
  biggest_string = format_userlist(biggest_names)

  new_names_count = 3
  new_names = updated - known
  sampled_names = list(random.sample(new_names, min(new_names_count, len(new_names))))
  sampled_names = [f'@{x}' for x in sampled_names]
  if len(new_names) > new_names_count:
    sampled_names.append('the rest')
  new_names_string = format_userlist(sampled_names)
  with open(config.knownfilepath, 'w') as knownfile:
    knownfile.writelines([f'{x}\n' for x in updated])

  return f"""

Closed at {datetime.datetime.strftime(datetime.datetime.now(), '%H:%M, %b %d')}

- Max intensity was {max_intensity} (from {biggest_string})
- Average intensity was ~{int(total/count)} across {count} triggers
- {len(new_names) if len(new_names) > 0 else "No"} new visitors this time!{f" (Hi {new_names_string}!)" if len(new_names_string) > 0 else " :("}
"""

##################################################################
# Start monitoring. Pass our two methods to the harness, along with our saved last_action_id if we have one.
##################################################################

print(f'Scaler is {scaler}')

bzz = Bzz(parse, act, config_file='config.json', stats_function=generate_stats)

arg = sys.argv[1] if len(sys.argv) > 1 else ''

if arg == 'closepost':
  bzz.close_post()
  exit()
elif arg == 'newpost':
  bzz.create_post()
else:
  bzz.attach_to_post()

bzz.run()
