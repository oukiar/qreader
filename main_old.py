'''
Qrcode example application
==========================

Original Author: Mathieu Virbel <mat@meltingrocks.com>
Adapted by: Oscar Alcantara <oukiar@gmail.com>

Featuring:

- Android camera initialization
- Show the android camera into a Android surface that act as an overlay
- New AndroidWidgetHolder that control any android view as an overlay
- New ZbarQrcodeDetector that use AndroidCamera / PreviewFrame + zbar to
  detect Qrcode.

'''


__version__ = '1.0'

from collections import namedtuple
from kivy.lang import Builder
from kivy.app import App
from kivy.properties import ObjectProperty, ListProperty, BooleanProperty, \
    NumericProperty, StringProperty
from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.popup import Popup
from kivy.graphics import Color, Line

from devslib.utils import ImageButton
from devslib.utils import MessageBoxTime

from kivy.uix.image import Image
from kivy.uix.bubble import Bubble
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown

from plyer import vibrator

import os


from jnius import autoclass, PythonJavaClass, java_method, cast
from android.runnable import run_on_ui_thread

# preload java classes
System = autoclass('java.lang.System')
System.loadLibrary('iconv')
PythonActivity = autoclass('org.renpy.android.PythonActivity')
Camera = autoclass('android.hardware.Camera')
ImageScanner = autoclass('net.sourceforge.zbar.ImageScanner')
Config = autoclass('net.sourceforge.zbar.Config')
SurfaceView = autoclass('android.view.SurfaceView')
LayoutParams = autoclass('android.view.ViewGroup$LayoutParams')
ImageZBar = autoclass('net.sourceforge.zbar.Image')
ImageFormat = autoclass('android.graphics.ImageFormat')
LinearLayout = autoclass('android.widget.LinearLayout')
Symbol = autoclass('net.sourceforge.zbar.Symbol')


class PreviewCallback(PythonJavaClass):
    '''Interface used to get back the preview frame of the Android Camera
    '''
    __javainterfaces__ = ('android.hardware.Camera$PreviewCallback', )

    def __init__(self, callback):
        super(PreviewCallback, self).__init__()
        self.callback = callback

    @java_method('([BLandroid/hardware/Camera;)V')
    def onPreviewFrame(self, data, camera):
        self.callback(camera, data)


class SurfaceHolderCallback(PythonJavaClass):
    '''Interface used to know exactly when the Surface used for the Android
    Camera will be created and changed.
    '''

    __javainterfaces__ = ('android.view.SurfaceHolder$Callback', )

    def __init__(self, callback):
        super(SurfaceHolderCallback, self).__init__()
        self.callback = callback
 
    @java_method('(Landroid/view/SurfaceHolder;III)V')
    def surfaceChanged(self, surface, fmt, width, height):
        self.callback(fmt, width, height)

    @java_method('(Landroid/view/SurfaceHolder;)V')
    def surfaceCreated(self, surface):
        pass
 
    @java_method('(Landroid/view/SurfaceHolder;)V')
    def surfaceDestroyed(self, surface):
        pass

  
class AndroidWidgetHolder(Widget):
    '''Act as a placeholder for an Android widget.
    It will automatically add / remove the android view depending if the widget
    view is set or not. The android view will act as an overlay, so any graphics
    instruction in this area will be covered by the overlay.
    '''

    view = ObjectProperty(allownone=True)
    '''Must be an Android View
    '''

    def __init__(self, **kwargs):
        self._old_view = None
        from kivy.core.window import Window
        self._window = Window
        kwargs['size_hint'] = (None, None)
        super(AndroidWidgetHolder, self).__init__(**kwargs)

    def on_view(self, instance, view):
        if self._old_view is not None:
            layout = cast(LinearLayout, self._old_view.getParent())
            layout.removeView(self._old_view)
            self._old_view = None

        if view is None:
            return

        activity = PythonActivity.mActivity
        activity.addContentView(view, LayoutParams(*self.size))
        view.setZOrderOnTop(True)
        view.setX(self.x)
        #view.setY(self._window.height - self.y - self.height)  #center screen
        view.setY(100)
        self._old_view = view

    def on_size(self, instance, size):
        if self.view:
            params = self.view.getLayoutParams()
            params.width = self.width
            params.height = self.height
            self.view.setLayoutParams(params)
            self.view.setY(self._window.height - self.y - self.height)

    def on_x(self, instance, x):
        if self.view:
            self.view.setX(x)

    def on_y(self, instance, y):
        if self.view:
            self.view.setY(self._window.height - self.y - self.height)


class AndroidCamera(Widget):
    '''Widget for controling an Android Camera.
    '''

    index = NumericProperty(0)

    __events__ = ('on_preview_frame', )

    def __init__(self, **kwargs):
        self._holder = None
        self._android_camera = None
        super(AndroidCamera, self).__init__(**kwargs)
        self._holder = AndroidWidgetHolder(size=self.size, pos=self.pos)
        self.add_widget(self._holder)

    @run_on_ui_thread
    def stop(self):
        if self._android_camera is None:
            return
        self._android_camera.setPreviewCallback(None)
        self._android_camera.release()
        self._android_camera = None
        self._holder.view = None

    @run_on_ui_thread
    def start(self):
        if self._android_camera is not None:
            return

        self._android_camera = Camera.open(self.index)
        

        # create a fake surfaceview to get the previewCallback working.
        self._android_surface = SurfaceView(PythonActivity.mActivity)
        surface_holder = self._android_surface.getHolder()

        # create our own surface holder to correctly call the next method when
        # the surface is ready
        self._android_surface_cb = SurfaceHolderCallback(self._on_surface_changed)
        surface_holder.addCallback(self._android_surface_cb)

        # attach the android surfaceview to our android widget holder
        self._holder.view = self._android_surface

    def _on_surface_changed(self, fmt, width, height):
        # internal, called when the android SurfaceView is ready
        # FIXME if the size is not handled by the camera, it will failed.
        params = self._android_camera.getParameters()
        params.setPreviewSize(width, height)
        self._android_camera.setParameters(params)
    
        self._android_camera.setDisplayOrientation(90)
    
        # now that we know the camera size, we'll create 2 buffers for faster
        # result (using Callback buffer approach, as described in Camera android
        # documentation)
        # it also reduce the GC collection
        bpp = ImageFormat.getBitsPerPixel(params.getPreviewFormat()) / 8.
        buf = '\x00' * int(width * height * bpp)
        self._android_camera.addCallbackBuffer(buf)
        self._android_camera.addCallbackBuffer(buf)

        # create a PreviewCallback to get back the onPreviewFrame into python
        self._previewCallback = PreviewCallback(self._on_preview_frame)

        # connect everything and start the preview
        self._android_camera.setPreviewCallbackWithBuffer(self._previewCallback);
        self._android_camera.setPreviewDisplay(self._android_surface.getHolder())
        self._android_camera.startPreview();

    def _on_preview_frame(self, camera, data):
        # internal, called by the PreviewCallback when onPreviewFrame is
        # received
        self.dispatch('on_preview_frame', camera, data)
        # reintroduce the data buffer into the queue
        self._android_camera.addCallbackBuffer(data)

    def on_preview_frame(self, camera, data):
        pass

    def on_size(self, instance, size):
        if self._holder:
            self._holder.size = size

    def on_pos(self, instance, pos):
        if self._holder:
            self._holder.pos = pos




class ZbarQrcodeDetector(AnchorLayout):
    '''Widget that use the AndroidCamera and zbar to detect qrcode.
    When found, the `symbols` will be updated
    '''
    camera_size = ListProperty([320, 240])

    symbols = ListProperty([])

    # XXX can't work now, due to overlay.
    show_bounds = BooleanProperty(False)
    
    datadecoded = StringProperty()

    Qrcode = namedtuple('Qrcode',
            ['type', 'data', 'bounds', 'quality', 'count'])

    def __init__(self, **kwargs):
        super(ZbarQrcodeDetector, self).__init__(**kwargs)
        self._camera = AndroidCamera(
                size=self.camera_size,
                size_hint=(None, None))
        self._camera.bind(on_preview_frame=self._detect_qrcode_frame)
        self.add_widget(self._camera)

        # create a scanner used for detecting qrcode
        self._scanner = ImageScanner()
        self._scanner.setConfig(0, Config.ENABLE, 0)
        self._scanner.setConfig(Symbol.QRCODE, Config.ENABLE, 1)
        self._scanner.setConfig(0, Config.X_DENSITY, 3)
        self._scanner.setConfig(0, Config.Y_DENSITY, 3)

    def start(self):
        self._camera.start()

    def stop(self):
        self._camera.stop()

    def _detect_qrcode_frame(self, instance, camera, data):
        # the image we got by default from a camera is using the NV21 format
        # zbar only allow Y800/GREY image, so we first need to convert,
        # then start the detection on the image
        parameters = camera.getParameters()
        size = parameters.getPreviewSize()
        barcode = ImageZBar(size.width, size.height, 'NV21')
        barcode.setData(data)
        barcode = barcode.convert('Y800')

        result = self._scanner.scanImage(barcode)

        if result == 0:
            self.symbols = []
            return

        

        # we detected qrcode! extract and dispatch them
        symbols = []
        it = barcode.getSymbols().iterator()
        while it.hasNext():
            symbol = it.next()
            qrcode = ZbarQrcodeDetector.Qrcode(
                type=symbol.getType(),
                data=symbol.getData(),
                quality=symbol.getQuality(),
                count=symbol.getCount(),
                bounds=symbol.getBounds())
            symbols.append(qrcode)
            
            print symbol.getData()
            self.datadecoded = symbol.getData()

        self.symbols = symbols

    '''
    # can't work, due to the overlay.
    def on_symbols(self, instance, value):
        if self.show_bounds:
            self.update_bounds()

    def update_bounds(self):
        self.canvas.after.remove_group('bounds')
        if not self.symbols:
            return
        with self.canvas.after:
            Color(1, 0, 0, group='bounds')
            for symbol in self.symbols:
                x, y, w, h = symbol.bounds
                x = self._camera.right - x - w
                y = self._camera.top - y - h
                Line(rectangle=[x, y, w, h], group='bounds')
    '''

class LabelData(Popup):
    content = ObjectProperty()
    
    
class Warehouses(Object):
    pass
    
class Clients(Object):
    pass
    
class Detector(BoxLayout):
    
    detector = ObjectProperty()
    message = ObjectProperty()

class RepackForm(Popup):
    agent = ObjectProperty()
    consignee = ObjectProperty()
    zone = ObjectProperty()
    transport = ObjectProperty()
    contentnotes = ObjectProperty()
    generalnotes = ObjectProperty()
    internalnotes = ObjectProperty()
    
class LabelReceipt(BoxLayout):
    receipt = ObjectProperty()
    consignee = ObjectProperty()
    zone = ObjectProperty()
    volume = ObjectProperty()
    country = ObjectProperty()
    objectId = ObjectProperty()

class Repack(Popup):
    detector = ObjectProperty()
    message = ObjectProperty()
    boxlabels = ObjectProperty()
    
    labels = []
    
    def on_open(self):
        print "Opening"
        self.detector.start()
    
    def on_dismiss(self):
        print "Closing repack"
        self.detector.stop()
        
    def decoded(self, val):
        '''
        if self.message.text != "Labels: ":
            self.message.text += ", "
            
        self.message.text += val
        '''
        
        if val not in self.labels:
            self.labels.append(val)
            
            #obtener informacion del warehouse leido
            wh = Warehouses.Query.get(objectId=val)
            
            
            box = Bubble(size_hint_y=None, height=200)
                    
            labelreceipt = LabelReceipt()
            
            labelreceipt.receipt.text = "Receipt#: " + str(wh.Receipt)
            labelreceipt.zone.text = "Zone: " + wh.Zone
            labelreceipt.volume.text = "Volume: " + wh.Volume
            labelreceipt.consignee.text = "[b]Consignee:[/b]\n" + wh.Consignee.Name
            labelreceipt.country.text = "Country: " + wh.Country
            labelreceipt.objectId.text = "ID: " + wh.objectId
            
            '''
            labelreceipt.zone.text = wh.Zone
            '''
                    
            #box.add_widget(Label(text="ID:"+val))
            box.add_widget(labelreceipt)
            
            if os.path.isfile("box.png"):
                print "BOX IMAGE FOUND"
                                
            self.boxlabels.add_widget( box )
            vibrator.vibrate(.2)

class Main(FloatLayout):
    pass

class QReader(FloatLayout):
    
    login = ObjectProperty()
    
    def signin(self):
        
        try:
            self.user = User.login(self.login.username.text, self.login.password.text)
        
            self.remove_widget(self.login)
            
            self.main = Main()
            self.add_widget(self.main)
        except:
            MessageBoxTime(msg="Bad login").open()
        
    
    def decoded(self, val):
        self.message.text = val
        
    def show_label(self):
        
        labeldata = LabelData()
        
        
        labelinfo = Warehouses.Query.get(objectId=self.message.text)
        
        print labelinfo, labelinfo.ReceiptDate

        for property, value in vars(labelinfo).iteritems():
            print property, ": ", value
            labeldata.content.add_widget(Label(text=str(property) ) )
            labeldata.content.add_widget(Label(text=str(value) ) )

        '''
        labeldata.receipt.text = str(labelinfo.Receipt)
        labeldata.status.text = labelinfo.Status
        labeldata.receiptDate.text = str(labelinfo.ReceiptDate)
        labeldata.agent.text = labelinfo.Agent
        labeldata.shipper.text = labelinfo.Shipper.Name
        labeldata.consignee.text = labelinfo.Consignee.Name
        '''
        
        labeldata.open()
        
    def on_repack(self):
        print "Repack !"
        
        self.repack = Repack()
        self.repack.open()
        
    def repack_done(self):
        self.repack.dismiss()
        
        #open the repack dialog information
        self.repackform = RepackForm()
        self.repackform.open()
        
    def repack_save(self):
        self.repackform.dismiss()
        
        wh = Warehouses()
        wh.Agent = self.repackform.agent.text
        #wh.Consignee.Name = self.repackform.consignee.text
        wh.Zone = self.repackform.zone.text
        wh.Transport = self.repackform.transport.text
        wh.Content = self.repackform.contentnotes.text
        wh.GeneralNotes = self.repackform.generalnotes.text
        wh.InternalNotes = self.repackform.internalnotes.text

        wh.save()
        
    def do_clientcomplete(self, w):
        print w.text
        
        clients = Clients.Query.all()

        #for the autocomplete
        if not hasattr(self, "down"):
            self.down = DropDown()

        self.down.clear_widgets()

        for client in clients:
            if w.text.lower() in client.Name.lower():
                print client.Name
                
                but = Button(text=client.Name, size_hint_y=None, height=44, on_press=self.select_clientresult)
                
                self.down.add_widget(but)
                
        self.down.open(self.repackform.consignee)

    def select_clientresult(self, w):
        print w.text
        

if __name__ == '__main__':

    class QReaderApp(App):
        def build(self):
                        
            return QReader()
            
        def on_stop(self):
            pass
        
            
        def on_pause(self):
            return True
            
        def on_resume(self):
            pass
        
    QReaderApp().run()
