// The parts that talk to the operating system directly. Following a dragged tab
// between windows needs the real mouse, which is read through macOS APIs; on
// other systems a tab can still be reordered, but not dragged out.

use tauri::{Runtime, WebviewWindow};

// Runs `f` with the window's NSWindow on the main thread, where AppKit must
// be called.
#[cfg(target_os = "macos")]
fn with_ns_window<R: Runtime>(window: &WebviewWindow<R>, f: impl FnOnce(&objc2::runtime::AnyObject) + Send + 'static) {
    let w = window.clone();
    let _ = window.run_on_main_thread(move || {
        let Ok(ns_window) = w.ns_window() else { return };
        let ns_window = ns_window as *mut objc2::runtime::AnyObject;
        if !ns_window.is_null() {
            f(unsafe { &*ns_window });
        }
    });
}

#[cfg(target_os = "macos")]
pub(crate) fn set_alpha<R: Runtime>(window: &WebviewWindow<R>, alpha: f64) {
    with_ns_window(window, move |w| unsafe {
        let _: () = objc2::msg_send![w, setAlphaValue: alpha];
    });
}

#[cfg(not(target_os = "macos"))]
pub(crate) fn set_alpha<R: Runtime>(_window: &WebviewWindow<R>, _alpha: f64) {}

// A dialog's window, attached to the window that asked: it moves with it and
// stays above it. macOS orders the child in as it attaches, so this shows it.
#[cfg(target_os = "macos")]
pub(crate) fn attach_child<R: Runtime>(parent: &WebviewWindow<R>, child: &WebviewWindow<R>) {
    let Ok(p) = parent.ns_window() else {
        let _ = child.show();
        return;
    };
    let p = p as usize;
    with_ns_window(child, move |c| unsafe {
        let p = p as *mut objc2::runtime::AnyObject;
        if !p.is_null() {
            // [parent addChildWindow:child ordered:NSWindowAbove]
            let _: () = objc2::msg_send![&*p, addChildWindow: c, ordered: 1isize];
        }
    });
}

// Elsewhere it was made the owner's at its start: showing it is enough.
#[cfg(not(target_os = "macos"))]
pub(crate) fn attach_child<R: Runtime>(_parent: &WebviewWindow<R>, child: &WebviewWindow<R>) {
    let _ = child.show();
}

pub(crate) const CAN_DRAG_OUT: bool = cfg!(target_os = "macos");

// The real mouse, read from the window server. Page events stop at the edge
// of the page; this keeps working anywhere on screen.
#[cfg(target_os = "macos")]
pub(crate) mod mouse {
    use std::ffi::c_void;

    #[repr(C)]
    struct CGPoint {
        x: f64,
        y: f64,
    }

    const COMBINED_SESSION_STATE: i32 = 0;
    const LEFT_BUTTON: u32 = 0;

    #[link(name = "CoreGraphics", kind = "framework")]
    extern "C" {
        fn CGEventCreate(source: *const c_void) -> *mut c_void;
        fn CGEventGetLocation(event: *mut c_void) -> CGPoint;
        fn CGEventSourceButtonState(state: i32, button: u32) -> bool;
    }

    #[link(name = "CoreFoundation", kind = "framework")]
    extern "C" {
        fn CFRelease(object: *const c_void);
    }

    pub fn location() -> (f64, f64) {
        unsafe {
            let event = CGEventCreate(std::ptr::null());
            if event.is_null() {
                return (0.0, 0.0);
            }
            let point = CGEventGetLocation(event);
            CFRelease(event);
            (point.x, point.y)
        }
    }

    pub fn left_pressed() -> bool {
        unsafe { CGEventSourceButtonState(COMBINED_SESSION_STATE, LEFT_BUTTON) }
    }
}

#[cfg(not(target_os = "macos"))]
pub(crate) mod mouse {
    pub fn location() -> (f64, f64) {
        (0.0, 0.0)
    }

    pub fn left_pressed() -> bool {
        false
    }
}
