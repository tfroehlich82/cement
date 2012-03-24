"""Cement core application module."""

import re
import sys
import signal

from cement2.core import backend, exc, handler, hook, log, config, plugin
from cement2.core import output, extension, arg, controller, meta
from cement2.lib import ext_configparser, ext_argparse, ext_logging
from cement2.lib import ext_nulloutput, ext_plugin

Log = backend.minimal_logger(__name__)    
    
class NullOut():
    def write(self, s):
        pass
        
def cement_signal_handler(signum, frame):
    """
    Catch a signal, run the cement_signal_hook, and then raise an exception 
    allowing the app to handle logic elsewhere.
    
    """      
    Log.debug('Caught signal %s' % signum)  
    
    for res in hook.run('cement_signal_hook', signum, frame):
        pass
        
    raise exc.CementSignalError(signum, frame)
                 
class CementApp(meta.MetaMixin):
    """
    The CementApp is the primary application class used and returned by
    lay_cement().
    
    Required Arguments:
    
        name
            The name of the application.
            
    Optional Arguments:
    
        argv
            A list of arguments to use.  Default: sys.argv
            
        defaults
            Default configuration dictionary.
            
        catch_signals
            List of signals to catch, and raise exc.CementSignalError for.
            Default: [signal.SIGTERM, signal.SIGINT]
                
        signal_handler
            Func to handle any caught signals. 
            Default: cement.core.foundation.cement_signal_handler
            
        config_handler
            An instantiated config handler object.
            
        extension_handler
            An instantiated extension handler object.
        
        log_handler
            An instantiated log handler object.
            
        plugin_handler
            An instantiated plugin handler object.
        
        arg_handler
            An instantiated argument handler object.
        
        output_handler
            An instantiated output handler object.
            
    """
    class Meta:
        app_name = None
        config_files = []
        plugins = []
        plugin_config_dir = None
        argv = sys.argv[1:]
        defaults = backend.defaults()
        catch_signals = [signal.SIGTERM, signal.SIGINT]
        signal_handler = cement_signal_handler
        config_handler = ext_configparser.ConfigParserConfigHandler
        extension_handler = extension.CementExtensionHandler
        log_handler = ext_logging.LoggingLogHandler
        plugin_handler = ext_plugin.CementPluginHandler
        argument_handler = ext_argparse.ArgParseArgumentHandler
        output_handler = ext_nulloutput.NullOutputHandler
        controller_handler = None
        extensions = []        
        core_extensions = [  
            'cement2.ext.ext_nulloutput',
            'cement2.ext.ext_plugin',
            'cement2.ext.ext_configparser', 
            'cement2.ext.ext_logging', 
            'cement2.ext.ext_argparse',
            ]
            
    def __init__(self, name=None, **kw):                
        super(CementApp, self).__init__(**kw)
        
        # for convenience we translate this to _meta
        if name:
            self._meta.app_name = name
        self._validate_name()
        
        self.ext = None
        self.config = None
        self.log = None
        self.plugin = None
        self.args = None
        self.output = None
        self.controller = None
        
        #self.defaults = kw.get('defaults', backend.defaults(self._meta.app_name))
        #self.defaults['base']['app_name'] = self._meta.app_name
        #self.argv = kw.get('argv', sys.argv[1:])
        #self.catch_signals = kw.get('catch_signals', 
        #                            [signal.SIGTERM, signal.SIGINT])
        #self.signal_handler = kw.get('signal_handler', cement_signal_handler)
        
        # initialize handlers if passed in and set config to reflect
        #if kw.get('config_handler', None):
        #    self.config = kw['config_handler']
        #
        #if kw.get('extension_handler', None):
        #    self.ext = kw['extension_handler']
        #                    
        #if kw.get('log_handler', None):
        #    self.log = kw['log_handler']
        #                            
        #if kw.get('plugin_handler', None):
        #    self.plugin = kw['plugin_handler']
        #       
        #if kw.get('arg_handler', None):
        #    self.args = kw['arg_handler']
        #    
        #if kw.get('output_handler', None):
        #    self.output = kw['output_handler']
        
        self._lay_cement()
        
    def _validate_name(self):
        if not self._meta.app_name:
            raise exc.CementRuntimeError("Application name missing.")
        
        # validate the name is ok
        ok = ['_']
        for char in self._meta.app_name:
            if char in ok:
                continue
            
            if not char.isalnum():
                raise exc.CementRuntimeError(
                    "App name can only contain alpha-numeric, or underscores."
                    )
                    
    def setup(self):
        """
        This function wraps all '_setup' actons in one call.  It is called
        before self.run(), allowing the application to be _setup but not
        executed (possibly letting the developer perform other actions
        before full execution.).
        
        All handlers should be instantiated and callable after _setup() is
        complete.
        
        """
        Log.debug("now setting up the '%s' application" % self._meta.app_name)
        
        for res in hook.run('cement_pre_setup_hook', self):
            pass
        
        self._setup_signals()
        self._setup_extension_handler()
        self._setup_config_handler()
        self._validate_required_config()
        self.validate_config()
        self._setup_log_handler()
        self._setup_plugin_handler()
        self._setup_arg_handler()
        self._setup_output_handler()
        self._setup_controller_handler()

        for res in hook.run('cement_post_setup_hook', self):
            pass
             
    def run(self):
        """
        This function wraps everything together (after self._setup() is 
        called) to run the application.
        
        """
        for res in hook.run('cement_pre_run_hook', self):
            pass
        
        # If controller exists, then pass controll to it
        if self.controller:
            self.controller._dispatch()
        else:
            self._parse_args()

        for res in hook.run('cement_post_run_hook', self):
            pass

    def close(self):
        """
        Close the application.  This runs the cement_on_close_hook() allowing
        plugins/extensions/etc to 'cleanup' at the end of program execution.
        
        """
        Log.debug("closing the application")
        for res in hook.run('cement_on_close_hook', self):
            pass
            
    def render(self, data, template=None):
        """
        This is a simple wrapper around self.output.render() which simply
        returns an empty string if no self.output handler is defined.
        
        Required Arguments:
        
            data
                The data dictionary to render.
                
        Optional Arguments:
        
            template
                The template to render to.  Default: None (some output 
                handlers do not use templates).
                
        """
        for res in hook.run('cement_pre_render_hook', self, data):
            if not type(res) is dict:
                Log.debug("pre_render_hook did not return a dict().")
            else:
                data = res
            
        if not self.output:
            Log.debug('render() called, but no output handler defined.')
            out_text = ''
        else:
            out_text = self.output.render(data, template)
            
        for res in hook.run('cement_post_render_hook', self, out_text):
            if not type(res) is str:
                Log.debug('post_render_hook did not return a str()')
            else:
                out_text = str(res)
        
        return out_text
        
    @property
    def pargs(self):
        """
        A shortcut for self.args.parsed_args.
        """
        return self.args.parsed_args
     
    def add_arg(self, *args, **kw):
        """
        A shortcut for self.args.add_argument.
        
        """   
        self.args.add_argument(*args, **kw)
        
    def _lay_cement(self):
        """
        Initialize the framework.
        """
        Log.debug("laying cement for the '%s' application" % \
                  self._meta.app_name)

        # hacks to suppress console output
        suppress_output = False
        if '--debug' in self._meta.argv:
            self._meta.defaults['base']['debug'] = True
        else:
            for flag in ['--quiet', '--json', '--yaml']:
                if flag in self._meta.argv:
                    suppress_output = True
                    break

        if suppress_output:
            Log.debug('suppressing all console output per runtime config')
            backend.SAVED_STDOUT = sys.stdout
            backend.SAVED_STDERR = sys.stderr
            sys.stdout = NullOut()
            sys.stderr = NullOut()
            
        # start clean
        backend.hooks = {}
        backend.handlers = {}

        # define framework hooks
        hook.define('cement_pre_setup_hook')
        hook.define('cement_post_setup_hook')
        hook.define('cement_pre_run_hook')
        hook.define('cement_post_run_hook')
        hook.define('cement_on_close_hook')
        hook.define('cement_signal_hook')
        hook.define('cement_pre_render_hook')
        hook.define('cement_post_render_hook')
    
        # define and register handlers    
        handler.define(extension.IExtension)
        handler.define(log.ILog)
        handler.define(config.IConfig)
        handler.define(plugin.IPlugin)
        handler.define(output.IOutput)
        handler.define(arg.IArgument)
        handler.define(controller.IController)
    
        # extension handler is the only thing that can't be loaded... as, 
        # well, an extension.  ;)
        handler.register(extension.CementExtensionHandler)
    
        #app = klass(name, defaults=defaults, *args, **kw)
        #return app
    
    def _set_handler_defaults(self, handler_obj):
        """
        Set config defaults per handler defaults if the config key is not 
        already set.  The configurations are set under a [section] whose
        name is that of the handlers interface type/label.  The exception
        is for handlers of type 'controllers', by which case the label of the
        controller is used.
        
        Required Arguments:
        
            handler_obj
                An instantiated handler object.
                
        """
        if not hasattr(handler_obj._meta, 'defaults'):
            Log.debug("no config defaults from '%s'" % handler_obj)
            return 
        
        Log.debug("setting config defaults from '%s'" % handler_obj)
        
        dict_obj = dict()
        handler_type = handler_obj._meta.interface.IMeta.label
        
        if handler_type == 'controller':
            # If its stacked, then add the defaults to the parent config
            if getattr(handler_obj._meta, 'stacked_on', None):
                key = handler_obj._meta.stacked_on
            else:
                key = handler_obj._meta.label
        else:
            key = handler_type
            
        dict_obj[key] = handler_obj._meta.defaults
        self.config.merge(dict_obj, override=False)
            
    def _parse_args(self):
        self.args.parse(self.argv)
        
        for member in dir(self.args.parsed_args):
            if member and member.startswith('_'):
                continue
            
            # don't override config values for options that weren't passed
            # or in otherwords are None
            elif getattr(self.args.parsed_args, member) is None:
                continue
                
            for section in self.config.get_sections():
                if member in self.config.keys(section):
                    self.config.set(section, member, 
                                    getattr(self.args.parsed_args, member))
        
        # If the output handler was changed after parsing args, then
        # we need to set it up again.
        if self.output:
            if self.config.get('base', 'output_handler') \
                != self.output._meta.label:
                self.output = None
                self._setup_output_handler()
        else:
            self._setup_output_handler()
            
    def _setup_signals(self):
        if not self._meta.catch_signals:
            Log.debug("catch_signals=None... not handling any signals")
            return
            
        for signum in self._meta.catch_signals:
            Log.debug("adding signal handler for signal %s" % signum)
            signal.signal(signum, self._meta.signal_handler)
    
    def _resolve_handler(self, handler_type, handler_def):
        """
        Resolves the actual handler as it can be either a string identifying
        the handler to load from backend.handlers, or it can be an 
        instantiated or non-instantiated handler class.
        
        Returns: The instantiated handler object.
        
        """
        han = None
        if type(handler_def) == str:
            han = handler.get(handler_type, handler_def)
        elif hasattr(handler_def, '_meta'):
            if not handler.registered(handler_type, handler_def._meta.label):
                handler.register(handler_def.__class__)
            han = handler_def
        elif hasattr(handler_def, 'Meta'):
            if not handler.registered(handler_type, handler_def.Meta.label):
                handler.register(handler_def)
            han = handler_def()

        self._set_handler_defaults(han)
        han._setup(self)
        return han
            
    def _setup_extension_handler(self):
        Log.debug("setting up %s.extension handler" % self._meta.app_name) 
        self.ext = self._resolve_handler('extension', 
                                         self._meta.extension_handler)
        self.ext.load_extensions(self._meta.core_extensions)
        self.ext.load_extensions(self._meta.extensions)
        
    def _setup_config_handler(self):
        Log.debug("setting up %s.config handler" % self._meta.app_name)
        self.config = self._resolve_handler('config', 
                                            self._meta.config_handler)
        for _file in self._meta.config_files:
            self.config.parse_file(_file)
                                  
    def _setup_log_handler(self):
        Log.debug("setting up %s.log handler" % self._meta.app_name)
        self.log = self._resolve_handler('log', self._meta.log_handler)
           
    def _setup_plugin_handler(self):
        Log.debug("setting up %s.plugin handler" % self._meta.app_name) 
        self.plugin = self._resolve_handler('plugin', 
                                            self._meta.plugin_handler)
        self.plugin.load_plugins(self.config.get('base', 'plugins'))
        
    def _setup_output_handler(self):
        Log.debug("setting up %s.output handler" % self._meta.app_name) 
        if not self.output:
            if not self.config.get('base', 'output_handler'):
                return
            h = handler.get('output', 
                            self.config.get('base', 'output_handler'))
            self.output = h()
        self._set_handler_defaults(self.output)
        self.output._setup(self.config)
         
    def _setup_arg_handler(self):
        Log.debug("setting up %s.arg handler" % self._meta.app_name) 
        if not self.args:
            h = handler.get('argument', 
                            self.config.get('base', 'arg_handler'))
            self.args = h()
        self._set_handler_defaults(self.args)
        self.args._setup(self.config)
        self.args.add_argument('--debug', dest='debug', 
            action='store_true', help='toggle debug output')
        self.args.add_argument('--quiet', dest='suppress_output', 
            action='store_true', help='suppress all output')
                 
    def _setup_controller_handler(self):
        Log.debug("setting up %s.controller handler" % self._meta.app_name) 

        # set handler defaults for all controllers
        for contr in handler.list('controller'):
            self._set_handler_defaults(contr())
            
        # Use self.controller first(it was passed in)
        if not self.controller:
            # Only use the config'd controller if no self.controller
            h = handler.get('controller', 
                            self.config.get('base', 'controller_handler'), 
                            None)
            if h:
                self.controller = h()
                
        # Trump all with whats passed at the command line, and pop off the
        # arg
        if len(self.argv) > 0:
            # translate dashes to underscore
            contr = re.sub('-', '_', self.argv[0])
            
            h = handler.get('controller', contr, None)
            if h:
                self.controller = h()
                self.argv.pop(0)

        # if no handler can be found, that's ok
        if self.controller:
            self.controller._setup(self)
        else:
            Log.debug("no controller could be found.")
    
    def _validate_required_config(self):
        """
        Validate base config settings required by cement.
        """
        Log.debug("validating required configuration parameters")
        
    def validate_config(self):
        """
        Validate application config settings.
        """
        pass
        
        
def lay_cement(name, klass=CementApp, *args, **kw):
    """
    Initialize the framework.  All args, and kwargs are passed to the 
    klass() object.

    Required Arguments:
    
        name
            The name of the application.


    Optional Keyword Arguments:

        klass
            The 'CementApp' class to instantiate and return.
            
        defaults
            The default config dictionary, other wise use backend.defaults().
            
        argv
            List of command line arguments.  Default: sys.argv.
            
    """
    Log.debug("laying cement for the '%s' application" % name)
    
    if kw.get('defaults', None):
        defaults = kw['defaults']
        del kw['defaults']
    else:
        defaults = backend.defaults(name)
        
    argv = kw.get('argv', sys.argv[1:])

    # basic logging _setup first (mostly for debug/error)
    suppress_output = False
    if '--debug' in argv:
        defaults['base']['debug'] = True
    elif '--quiet' in argv:
        suppress_output = True
        
    elif '--json' in argv or '--yaml' in argv:
        # The framework doesn't provide --json/--yaml options but rather
        # extensions do.  That said, the --json/--yaml extensions are shipped
        # with our source so we can add a few hacks here.
        suppress_output = True
        
    # a hack to suppress output
    if suppress_output:
        backend.SAVED_STDOUT = sys.stdout
        backend.SAVED_STDERR = sys.stderr
        sys.stdout = NullOut()
        sys.stderr = NullOut()
        
    # start clean
    backend.hooks = {}
    backend.handlers = {}

    # define framework hooks
    hook.define('cement_pre_setup_hook')
    hook.define('cement_post_setup_hook')
    hook.define('cement_pre_run_hook')
    hook.define('cement_post_run_hook')
    hook.define('cement_on_close_hook')
    hook.define('cement_signal_hook')
    hook.define('cement_pre_render_hook')
    hook.define('cement_post_render_hook')
    
    # define and register handlers    
    handler.define(extension.IExtension)
    handler.define(log.ILog)
    handler.define(config.IConfig)
    handler.define(plugin.IPlugin)
    handler.define(output.IOutput)
    handler.define(arg.IArgument)
    handler.define(controller.IController)
    
    # extension handler is the only thing that can't be loaded... as, well, an
    # extension.  ;)
    handler.register(extension.CementExtensionHandler)
    
    app = klass(name, defaults=defaults, *args, **kw)
    return app

