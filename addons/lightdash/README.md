A lightweight, self-contained dashboard renderer for Home Assistant. Instead of running HA's full Lovelace frontend, which is a struggle for low-power devices such as NSPanels and older Android tablets, LightDash is a focused alternative: support for tiles and built-in entities, intelligent mapping of some common custom cards to lightweight alternatives, and plain HTML + CSS with much of the interactivity shifted to the addon itself.

I orignally built LightDash to run on the NSPanel Pro in-wall touchscreens I have around my house, which are getting increasingly slow as the HA team add more dashboard capabilities. Wonderful for iPads, desktop browsing and recent smartphones, but almost unusable on the devices that sit in the gap between ESPHome and modern browsers.

LightDash is designed to handle copy-and-pasted YAML from existing dashboards with _minimal_ (not quite zero) adjustment - there's an edit-and-preview web UI accessible from the addon control panel, where you can tweak the YAML and see the results immediately before saving.

**Caveat 1:** I've focused on the cards I use in my own small-screen dashboards. I'd love for contributors to add support for their own layouts!

**Caveat 2:** Yep, I used OpenCode to build a lot of this. I'm a 25+ year software architect and developer, but this is a one-day project. I'm pretty happy it's not filled with slop - I've reviewed it and it's passable - but I make no warranties about code quality this early in its life.
