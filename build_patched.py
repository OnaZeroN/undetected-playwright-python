import sys
import undetected_playwright
import os
import pathlib
import re
import asyncio

from patch_check import main as patch_check_main


def patch_driver(path: str):
    print(f'[PATCH] patching driver for "{path}"', file=sys.stderr)

    def replace_in_file(file_path: str, pattern: str, repl: str):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            content_new = re.sub(pattern, repl, content, flags=re.MULTILINE | re.DOTALL)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content_new)

    server_path = os.path.join(path, "package", "lib", "server")
    chromium_path = os.path.join(server_path, "chromium")

    cr_devtools_path = os.path.join(chromium_path, "crDevTools.js")
    replace_in_file(cr_devtools_path, r"session\.send\('Runtime\.enable'\)", "/*$&*/")

    cr_page_path = os.path.join(chromium_path, "crPage.js")
    replace_in_file(cr_page_path, r"this\._client\.send\('Runtime\.enable', \{\}\),", "/*$&*/")
    replace_in_file(cr_page_path, r"session\._sendMayFail\('Runtime\.enable'\);", "/*$&*/")

    cr_sv_worker_path = os.path.join(chromium_path, "crServiceWorker.js")
    replace_in_file(cr_sv_worker_path, r"session\.send\('Runtime\.enable', \{\}\)\.catch\(e => \{\}\);", "/*$&*/")

    frames_path = os.path.join(server_path, "frames.js")

    with open(frames_path, "r", encoding="utf-8") as f:
        frames_js = f.read()

    custom_imports = """
// undetected-undetected_playwright-patch - custom imports
var _crExecutionContext = require('./chromium/crExecutionContext');
var _dom = require('./dom');
"""

    if custom_imports not in frames_js:
        frames_js = custom_imports + frames_js

    context_pattern = r"async _context\(world\) \{[\s\S]*?\}"
    new_context_function = """
async _context(world) {
    if (this._isolatedContexts == undefined) {
        this._isolatedContexts = new Map();
    }
    let context = this._isolatedContexts.get(world);
    if (!context) {
        var worldName = world._name; // Используем _name, если name недоступно
        var result = await this._page._delegate._mainFrameSession._client.send('Page.createIsolatedWorld', {
            frameId: this._id,
            grantUniveralAccess: true,
            worldName: worldName
        });
        var crContext = new _crExecutionContext.CRExecutionContext(this._page._delegate._mainFrameSession._client, { id: result.executionContextId });
        context = new _dom.FrameExecutionContext(crContext, this, worldName);
        this._isolatedContexts.set(world, context);
    }
    return context;
}
"""

    frames_js = re.sub(context_pattern, new_context_function, frames_js, flags=re.MULTILINE | re.DOTALL)

    clear_lifecycle_pattern = r"_onClearLifecycle\(\) \{[\s\S]*?\}"
    new_clear_lifecycle_function = """
_onClearLifecycle() {
    this._isolatedContexts = new Map();
}
"""

    frames_js = re.sub(clear_lifecycle_pattern, new_clear_lifecycle_function, frames_js, flags=re.MULTILINE | re.DOTALL)

    with open(frames_path, "w", encoding="utf-8") as f:
        f.write(frames_js)


def main(build: bool = True, build_all: bool = False):
    cmd = "python setup.py bdist_wheel"
    if build_all:
        cmd += " --all"
    if build:
        os.system(cmd)
    else:
        rel_path = "/driver"
        module_path = pathlib.Path(os.path.dirname(undetected_playwright.__file__) + rel_path)
        patch_driver(str(module_path))
        path = pathlib.Path(os.getcwd() + "/undetected_playwright" + rel_path)
        if module_path.resolve() != path.resolve():
            patch_driver(str(path))


if __name__ == "__main__":
    main(build=True, build_all=False)

    asyncio.run(patch_check_main())
