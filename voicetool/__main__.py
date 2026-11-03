import sys

if sys.platform == "darwin":
    from voicetool.mac.app import main
else:
    from voicetool.app import main

main()
