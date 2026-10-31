#import <AppKit/AppKit.h>
#import <ApplicationServices/ApplicationServices.h>
#import <CoreGraphics/CoreGraphics.h>

static CGRect area;
static unsigned buttons=0;
static CGEventFlags flags=0;
static NSMutableSet *held;
static NSDictionary *codes;
static void post(CGEventRef e) { if(e){CGEventSetFlags(e,flags);CGEventPost(kCGHIDEventTap,e);CFRelease(e);} }
static void key(unsigned code,BOOL down) {
 CGEventRef e=CGEventCreateKeyboardEvent(NULL,(CGKeyCode)code,down);post(e);
 if(down)[held addObject:@(code)];else [held removeObject:@(code)];
}
static void reset(void) {
 flags=0; for(NSNumber *n in [held copy])key([n unsignedIntValue],NO);
 CGEventRef current=CGEventCreate(NULL);CGPoint p=current?CGEventGetLocation(current):CGPointZero;if(current)CFRelease(current);
 for(unsigned i=0;i<3;i++)if(buttons&(1<<i))post(CGEventCreateMouseEvent(NULL,i==0?kCGEventLeftMouseUp:i==1?kCGEventRightMouseUp:kCGEventOtherMouseUp,p,i==0?kCGMouseButtonLeft:i==1?kCGMouseButtonRight:kCGMouseButtonCenter));
 buttons=0;
}
static void screenArea(void) {
 CGDirectDisplayID ids[32];uint32_t n=0;CGGetActiveDisplayList(32,ids,&n);area=CGRectNull;
 for(unsigned i=0;i<n;i++)area=CGRectUnion(area,CGDisplayBounds(ids[i]));
 if(CGRectIsNull(area))area=CGDisplayBounds(CGMainDisplayID());
}
static NSDictionary *run(NSDictionary *m) {
 NSString *type=m[@"type"];
 if([type isEqual:@"frame"]){
  if(!AXIsProcessTrusted())return @{@"error":@"accessibility permission required"};
  if(@available(macOS 10.15,*)){if(!CGPreflightScreenCaptureAccess())return @{@"error":@"screen permission required"};}
  screenArea();
  CGImageRef shot=CGWindowListCreateImage(area,kCGWindowListOptionOnScreenOnly,kCGNullWindowID,kCGWindowImageDefault);
  if(!shot)return @{@"error":@"capture unavailable"};
  size_t w=CGImageGetWidth(shot),h=CGImageGetHeight(shot);
  double limit=[m[@"width"] doubleValue];if(limit<640||limit>1600)limit=1600;
  double scale=fmin(1.0,limit/w);size_t tw=fmax(1,w*scale),th=fmax(1,h*scale);
  NSBitmapImageRep *rep=[[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:tw pixelsHigh:th bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace bytesPerRow:0 bitsPerPixel:0];
  NSGraphicsContext *gc=[NSGraphicsContext graphicsContextWithBitmapImageRep:rep];
  [NSGraphicsContext saveGraphicsState];[NSGraphicsContext setCurrentContext:gc];
  CGContextDrawImage(gc.CGContext,CGRectMake(0,0,tw,th),shot);
  [NSGraphicsContext restoreGraphicsState];CGImageRelease(shot);
  NSData *jpg=[rep representationUsingType:NSBitmapImageFileTypeJPEG properties:@{NSImageCompressionFactor:@(([m[@"quality"] intValue]>=35&&[m[@"quality"] intValue]<=80)?[m[@"quality"] doubleValue]/100.0:0.65)}];
  if(!jpg)return @{@"error":@"encode failed"};return @{@"image":[jpg base64EncodedStringWithOptions:0]};
 }
 if(!AXIsProcessTrusted())return @{@"error":@"accessibility permission required"};
 if([type isEqual:@"reset"]){reset();return @{};}
 if([type isEqual:@"pointer"]){
  CGPoint p=CGPointMake(area.origin.x+fmin(0.999999,fmax(0,[m[@"x"] doubleValue]))*area.size.width,area.origin.y+fmin(0.999999,fmax(0,[m[@"y"] doubleValue]))*area.size.height);
  unsigned next=[m[@"buttons"] unsignedIntValue]&7;
  for(unsigned i=0;i<3;i++)if((next^buttons)&(1<<i)){
   BOOL down=next&(1<<i);CGEventType t=i==0?(down?kCGEventLeftMouseDown:kCGEventLeftMouseUp):i==1?(down?kCGEventRightMouseDown:kCGEventRightMouseUp):(down?kCGEventOtherMouseDown:kCGEventOtherMouseUp);
   CGEventRef e=CGEventCreateMouseEvent(NULL,t,p,i==0?kCGMouseButtonLeft:i==1?kCGMouseButtonRight:kCGMouseButtonCenter);
   static CFAbsoluteTime last=0;static CGPoint prev;static int count=0;
   if(i==0&&down){CFAbsoluteTime now=CFAbsoluteTimeGetCurrent();count=(now-last<0.4&&hypot(p.x-prev.x,p.y-prev.y)<5)?count+1:1;last=now;prev=p;}
   if(i==0)CGEventSetIntegerValueField(e,kCGMouseEventClickState,count);post(e);
  }
  CGEventType motion=(next&1)?kCGEventLeftMouseDragged:(next&2)?kCGEventRightMouseDragged:(next&4)?kCGEventOtherMouseDragged:kCGEventMouseMoved;
  post(CGEventCreateMouseEvent(NULL,motion,p,(next&2)?kCGMouseButtonRight:(next&4)?kCGMouseButtonCenter:kCGMouseButtonLeft));buttons=next;
 }else if([type isEqual:@"wheel"]){post(CGEventCreateScrollWheelEvent(NULL,kCGScrollEventUnitPixel,2,-[m[@"dy"] intValue],-[m[@"dx"] intValue]));
 }else if([type isEqual:@"text"]){
  NSString *text=m[@"text"]?:@"";NSUInteger len=[text length];if(len>16384)return @{@"error":@"text too long"};
  UniChar *chars=calloc(len+1,sizeof(UniChar));[text getCharacters:chars range:NSMakeRange(0,len)];
  for(NSUInteger i=0;i<len;i+=16){NSUInteger n=MIN((NSUInteger)16,len-i);CGEventRef e=CGEventCreateKeyboardEvent(NULL,0,YES);CGEventKeyboardSetUnicodeString(e,n,chars+i);post(e);e=CGEventCreateKeyboardEvent(NULL,0,NO);CGEventKeyboardSetUnicodeString(e,n,chars+i);post(e);}free(chars);
 }else if([type isEqual:@"key"]){
  NSString *code=m[@"code"];NSNumber *n=codes[code];BOOL down=[m[@"down"] boolValue];
  if(n){CGEventFlags bit=0;if([code hasPrefix:@"Shift"])bit=kCGEventFlagMaskShift;else if([code hasPrefix:@"Control"])bit=kCGEventFlagMaskControl;else if([code hasPrefix:@"Alt"])bit=kCGEventFlagMaskAlternate;else if([code hasPrefix:@"Meta"])bit=kCGEventFlagMaskCommand;if(down)flags|=bit;else flags&=~bit;key([n unsignedIntValue],down);}
 }
 return @{};
}
int main(int argc,char **argv){@autoreleasepool{
 [NSApplication sharedApplication];[NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
 if(argc>1&&strcmp(argv[1],"--permissions")==0){
  if(@available(macOS 10.15,*)){CGRequestScreenCaptureAccess();}
  BOOL inputOK=AXIsProcessTrustedWithOptions((__bridge CFDictionaryRef)@{(__bridge NSString*)kAXTrustedCheckOptionPrompt:@YES});
  return inputOK&&CGPreflightScreenCaptureAccess()?0:1;
 }
 if(!CGPreflightScreenCaptureAccess())CGRequestScreenCaptureAccess();
 if(!AXIsProcessTrusted())AXIsProcessTrustedWithOptions((__bridge CFDictionaryRef)@{(__bridge NSString*)kAXTrustedCheckOptionPrompt:@YES});
 held=[NSMutableSet set];screenArea();
 codes=@{@"KeyA":@0,@"KeyS":@1,@"KeyD":@2,@"KeyF":@3,@"KeyH":@4,@"KeyG":@5,@"KeyZ":@6,@"KeyX":@7,@"KeyC":@8,@"KeyV":@9,@"KeyB":@11,@"KeyQ":@12,@"KeyW":@13,@"KeyE":@14,@"KeyR":@15,@"KeyY":@16,@"KeyT":@17,@"Digit1":@18,@"Digit2":@19,@"Digit3":@20,@"Digit4":@21,@"Digit6":@22,@"Digit5":@23,@"Equal":@24,@"Digit9":@25,@"Digit7":@26,@"Minus":@27,@"Digit8":@28,@"Digit0":@29,@"BracketRight":@30,@"KeyO":@31,@"KeyU":@32,@"BracketLeft":@33,@"KeyI":@34,@"KeyP":@35,@"Enter":@36,@"KeyL":@37,@"KeyJ":@38,@"Quote":@39,@"KeyK":@40,@"Semicolon":@41,@"Backslash":@42,@"Comma":@43,@"Slash":@44,@"KeyN":@45,@"KeyM":@46,@"Period":@47,@"Tab":@48,@"Space":@49,@"Backquote":@50,@"Backspace":@51,@"Escape":@53,@"MetaRight":@54,@"MetaLeft":@55,@"ShiftLeft":@56,@"CapsLock":@57,@"AltLeft":@58,@"ControlLeft":@59,@"ShiftRight":@60,@"AltRight":@61,@"ControlRight":@62,@"NumpadDecimal":@65,@"NumpadMultiply":@67,@"NumpadAdd":@69,@"NumpadDivide":@75,@"NumpadEnter":@76,@"NumpadSubtract":@78,@"Numpad0":@82,@"Numpad1":@83,@"Numpad2":@84,@"Numpad3":@85,@"Numpad4":@86,@"Numpad5":@87,@"Numpad6":@88,@"Numpad7":@89,@"Numpad8":@91,@"Numpad9":@92,@"F5":@96,@"F6":@97,@"F7":@98,@"F3":@99,@"F8":@100,@"F9":@101,@"F11":@103,@"F10":@109,@"F12":@111,@"Home":@115,@"PageUp":@116,@"Delete":@117,@"F4":@118,@"End":@119,@"F2":@120,@"PageDown":@121,@"F1":@122,@"ArrowLeft":@123,@"ArrowRight":@124,@"ArrowDown":@125,@"ArrowUp":@126};
 char *line=NULL;size_t cap=0;
 while(getline(&line,&cap,stdin)>0){@autoreleasepool{
  NSData *data=[[NSString stringWithUTF8String:line] dataUsingEncoding:NSUTF8StringEncoding];
  NSDictionary *m=[NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
  NSDictionary *out;@try{out=[m isKindOfClass:[NSDictionary class]]?run(m):@{@"error":@"invalid command"};}@catch(NSException *e){out=@{@"error":@"native screen unavailable"};}
  NSData *encoded=[NSJSONSerialization dataWithJSONObject:out options:0 error:NULL];fwrite(encoded.bytes,1,encoded.length,stdout);fputc('\n',stdout);fflush(stdout);
 }}free(line);reset();return 0;
}}
