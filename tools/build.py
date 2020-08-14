from __future__ import print_function

import os
import sys
import zipfile
import subprocess
import shutil
import platform

try:
    from urllib.request import urlopen, urlretrieve, Request
    from urllib.error import HTTPError
except ImportError:
    from urllib import urlretrieve
    from urllib2 import urlopen, Request

DEPOT_TOOLS_WIN = 'https://storage.googleapis.com/chrome-infra/depot_tools.zip'
DEPOT_TOOLS_REPO = 'https://chromium.googlesource.com/chromium/tools/depot_tools.git'
DEPOT_TOOLS_PATH = 'temp/depot_tools.zip'
DEPOT_TOOLS_DEST = 'depot_tools'

DART_SDK_VERSION = '2.9.1'

def Sync():
  os_name = platform.system()
  use_shell = os_name == 'Windows'

  if not os.path.exists('temp'):
    os.makedirs('temp')

  if os_name == 'Windows':
    os.environ['PATH'] = os.path.abspath(DEPOT_TOOLS_DEST) + ';' + os.environ.get('PATH')
    os.environ['DEPOT_TOOLS_WIN_TOOLCHAIN'] = '0'
  else:
    os.environ['PATH'] = os.environ.get('PATH') + ':' + os.path.abspath(DEPOT_TOOLS_DEST)

  if not os.path.exists(DEPOT_TOOLS_DEST):
    if os_name == 'Windows':
      os.makedirs(DEPOT_TOOLS_DEST)

      print('Downloading depot_tools for Windows')
      urlretrieve(DEPOT_TOOLS_WIN, DEPOT_TOOLS_PATH)

      print('Extracting depot_tools for Windows')
      with zipfile.ZipFile(DEPOT_TOOLS_PATH, 'r') as zf:
        zf.extractall(DEPOT_TOOLS_DEST)

        print('Bootstrapping depot_tools')
        process = subprocess.Popen(['gclient'], shell=use_shell)
        process.wait()
        if process.returncode != 0:
          print('Failed to bootstrap depot_tools')
          return 1
    else:
      print('Cloning depot_tools')
      process = subprocess.Popen(['git', 'clone', DEPOT_TOOLS_REPO], shell=use_shell)
      process.wait()
      if process.returncode != 0:
        print('Failed to clone depot_tools')
        return 1

  if not os.path.exists('sdk'):
    print('Fetching Dart SDK')
    process = subprocess.Popen(['fetch', 'dart'], shell=use_shell)
    process.wait()
    if process.returncode != 0:
      print('Failed to fetch the Dart SDK')
      return 1

  print('Checking Dart SDK version')
  process = subprocess.Popen(['git', 'describe', '--tags'], cwd='sdk', stdout=subprocess.PIPE, shell=use_shell)
  process_data = process.communicate()
  process.wait()
  if process.returncode != 0:
    print('Failed to check Dart SDK version')
    return 1

  if process_data[0].strip() != DART_SDK_VERSION:
    print('Updating Dart SDK')

    process = subprocess.Popen(['gclient', 'sync', '--with_branch_heads', '--with_tags'], cwd='sdk', shell=use_shell)
    process.wait()
    if process.returncode != 0:
      print('Failed to sync Dart SDK')
      return 1

    process = subprocess.Popen(['git', 'fetch', '--tags'], cwd='sdk', shell=use_shell)
    process.wait()
    if process.returncode != 0:
      print('Failed to fetch git tags')
      return 1

    process = subprocess.Popen(['git', 'stash'], cwd='sdk', shell=use_shell)
    process.wait()
    if process.returncode != 0:
      print('Failed to fetch git tags')
      return 1

    process = subprocess.Popen(['git', 'checkout', 'tags/' + DART_SDK_VERSION], cwd='sdk', shell=use_shell)
    process.wait()
    if process.returncode != 0:
      print('Failed to checkout tag')
      return 1

    process = subprocess.Popen(['gclient', 'sync', '-D', '--force', '--reset', '--with_branch_heads', '--with_tags'], cwd='sdk', shell=use_shell)
    process.wait()
    if process.returncode != 0:
      print('Failed to sync Dart SDK')
      return 1

  print('Dart SDK up to date')

  process = subprocess.Popen(['git', 'checkout', '--', 'BUILD.gn'], cwd='sdk', shell=use_shell)
  process.wait()
  if process.returncode != 0:
    print('Failed to reset Dart SDK')
    return 1

  process = subprocess.Popen(['git', 'checkout', '--', 'runtime/bin/BUILD.gn'], cwd='sdk', shell=use_shell)
  process.wait()
  if process.returncode != 0:
    print('Failed to reset Dart SDK')
    return 1

  # print('Updating build files'
  with open('sdk/BUILD.gn', 'a') as file:
    file.write(open('BUILD.gn', 'r').read())

  with open('sdk/runtime/bin/BUILD.gn', 'a') as file:
    file.write(open('src/BUILD.gn', 'r').read())

  print('Running build')
  process = subprocess.Popen(['python', 'tools/build.py', 'def'], cwd='sdk', shell=use_shell)
  process.wait()
  if process.returncode != 0:
    print('Dart SDK build failed')
    return 1

  print('Successfully built')

  if not os.path.exists('pkg'):
    os.makedirs('pkg')

  if not os.path.exists('pkg/include'):
    os.makedirs('pkg/include')

  if not os.path.exists('pkg/build'):
    os.makedirs('pkg/build')

  shutil.copy('sdk/out/DebugX64/libdef.dll', 'pkg/build/libdef.dll')
  shutil.copy('sdk/out/DebugX64/libdef.dll.lib', 'pkg/build/libdef.dll.lib')
  shutil.copy('sdk/out/DebugX64/libdef.dll.pdb', 'pkg/build/libdef.dll.pdb')

  shutil.copy('src/def.h', 'pkg/include/def.h')
  shutil.copy('sdk/runtime/include/dart_api.h', 'pkg/include/dart_api.h')
  shutil.copy('sdk/runtime/include/dart_native_api.h', 'pkg/include/dart_native_api.h')

  if not os.path.exists('pkg/gen_kernel.exe'):
    print('Building gen_kernel.exe')
    process = subprocess.Popen(['dart2native', '../sdk/pkg/vm/bin/gen_kernel.dart', '-o', 'gen_kernel.exe'], cwd='pkg', shell=use_shell)
    process.wait()
    if process.returncode != 0:
      print('Dart SDK build failed')
      return 1

  return 0

def Clean():
  if os.path.exists('temp'):
    shutil.rmtree('temp')

  if os.path.exists(DEPOT_TOOLS_DEST):
    shutil.rmtree(DEPOT_TOOLS_DEST)

  if os.path.exists('sdk'):
    shutil.rmtree('sdk')

  return 0


def main(argv):
  if len(argv) == 1 or argv[1] == 'build':
    return Sync()
  elif argv[1] == 'clean':
    return Clean()

if __name__ == '__main__':
  sys.exit(main(sys.argv))