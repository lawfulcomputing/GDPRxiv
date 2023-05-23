import os
import platform

class WebdriverExecPolicy():
    def get_system_path(self):
        system = platform.system()
        supported = ['Darwin', 'Linux', 'Windows']
        if system not in supported:
            raise ValueError('No chromedriver is supported for this platform system %s' % system)
        #return os.path.abspath("pygdpr/assets/chromedriver/%s" % system.lower())
        return os.path.abspath("pygdpr/assets/chromedriver")
