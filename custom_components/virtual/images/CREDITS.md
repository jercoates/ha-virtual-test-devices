# Test camera frames

These are the frames the virtual camera hands to Home Assistant. A real camera
returns whatever it is pointing at; this one cycles through these, so a piston
that takes two snapshots produces two visibly different pictures — which is how
you can tell it fired twice rather than once.

They are ordinary photographs rather than synthetic test cards on purpose: a
camera piston that resizes, attaches or notifies should be exercised against
the kind of image it will meet in service.

## Credit

Photographs by **Curtis J Coates**, included here under this package's GPL-3.0
licence.

## The video clip

`../video/camera_clip.mp4` is the clip behind the camera's live view and recording.
It is a security-camera recording released by the **FBI Honolulu office** of the
2009 tsunami reaching a parking lot in Pago Pago, American Samoa, from
[Wikimedia Commons](https://commons.wikimedia.org/wiki/File:FBI_tsunami_video_-_Pago_Pago_parking_lot_-_end.ogv).
Commons marks it public domain (a work of the US federal government, and a security
camera video with no human author), so no attribution is required; it is credited
here anyway. It was converted from Ogg Theora to H.264 MP4 (no audio, 22 s,
396x340) because Home Assistant's stream expects H.264. Replace the file with any
other small H.264 MP4 of the same name; remove it and live view is switched off.

## Replacing them

Drop JPEGs in this folder and remove the ones you don't want; the camera globs
the folder in sorted order, so nothing in the code needs changing. Keep them
small — these are ~30-65 KB at 640px, and they ship with every install.

Note that anything placed here is redistributed to every user under GPL-3.0,
which permits commercial use and modification. Only add images you are happy to
release on those terms.
