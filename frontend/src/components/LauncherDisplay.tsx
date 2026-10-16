import { displayOwner } from '../lib/display-owner';
import { renderLauncherDisplay } from './LauncherDisplayView';
export const launcherDisplay = displayOwner(renderLauncherDisplay);
export const LauncherDisplay = launcherDisplay.View;
