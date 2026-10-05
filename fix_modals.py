import re

with open("static/index.html", "r") as f:
    content = f.read()

# We need to target the inner div of each modal and make sure it has max-h-[90vh], flex, flex-col.
# Then we wrap its middle content in an overflow-y-auto container, or simply set overflow-y-auto on the whole inner div if it doesn't have a fixed footer we care about breaking out.

# But the user specifically asked: "fix buttons on lower part with scroll for center content"
# So the structure needs to be:
# <div class="modal inner max-h-[90vh] flex flex-col ...">
#   <h2>Title</h2>
#   <div class="overflow-y-auto flex-grow ..."> ... center content ... </div>
#   <div class="buttons border-t mt-auto ..."> ... buttons ... </div>
# </div>
