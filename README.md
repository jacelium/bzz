# Bzz

Hooks up a Mastodon post to any API that can receive calls from Python.

Just look at the config section and the parse/act methods. I've tried to make them pretty obvious!

The user is expected to provide their own `parse` and `act` methods, and optionally a `generate_stats` method for adding extra data to a post when it's closed.

# Usage
Just run `python3 app.py` for the example app. This shows the following usage through the `create_post()`, `attach_to_post()` and `close_post()` methods:
- `python3 app.py`: attaches to an existing linked post. If none is found, offers to create one based on config and attach to that, or accepts a defined post ID.
- `python3 app.py newpost`: clears context for current post and creates a new one as above. WARNING: if you run this and then ctrl-c before creating the new post, the old post's context is still deleted.
- `python3 app.py closepost`: attempts to 'close' the current post - appends a marker to its CWs and optionally generates statistics.

# TODO
- Proper configuration!
- ~Proper encapsulation! (Objectify that sucka)~
- Better state handling!
- ~Threaded poll/parse and act loops to allow for individual timings!~
  - Better threading handling now that we hvae threading
- Better examples!
- Formatting on the sample post display in-terminal!
- Checking if the specified post is 'closed' and ignoring inputs if so. For now you just have to remember to turn the script off!
