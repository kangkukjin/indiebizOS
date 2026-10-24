package com.indiebiz.phoneagent.update

import android.app.admin.DeviceAdminReceiver

/** Optional, explicitly USB-provisioned owner for unattended updates on dedicated devices.
 * No lock, wipe, account, camera, or password policies are requested or applied.
 */
class UpdateDeviceAdminReceiver : DeviceAdminReceiver()
