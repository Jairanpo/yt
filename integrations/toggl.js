// Toggl Track — custom integration for yt·local
//
// Install it once:
//   Toggl Track extension → Settings → Integrations → Development mode
//   → New integration. Name it "yt local", set the origin to your library's
//   address (http://127.0.0.1:8420 unless you moved the port), paste this in,
//   Save integration, and grant the permission it asks for.
//
// Nothing here reaches the network from the page. The extension does its own
// talking to Toggl, out of band, which is why the library's CSP can stay shut.
//
// What it reads, from the mount the player puts in while a video is open:
//   data-description  the channel, as you named it in the ⏱ toggl sheet
//   data-project      the Toggl project it counts towards
//   data-tags         comma separated tags
// All three are set per channel, not per video: one entry that says which
// creator you spent the time on. Blank fields fall back to the channel's own
// name, so a creator you never configured still tracks as itself.
//
// A project has to already exist in Toggl under that exact name — Toggl will
// not create one for you, and an unknown name is quietly dropped.

togglbutton.render('#ptoggl:not(.toggl)', {observe: true}, function (elem) {
  const tags = (elem.dataset.tags || '')
    .split(',')
    .map(t => t.trim())
    .filter(Boolean);

  const link = togglbutton.createTimerLink({
    className: 'ytlocal',
    description: elem.dataset.description,
    projectName: elem.dataset.project || undefined,
    tags: tags.length ? tags : undefined,
    buttonType: 'minimal'
  });

  elem.appendChild(link);
});
