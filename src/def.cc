// Copyright (c) 2020, the Dart project authors.  Please see the AUTHORS file
// for details. All rights reserved. Use of this source code is governed by a
// BSD-style license that can be found in the LICENSE file.

#include <cstdlib>
#include <fstream>
#include <iostream>
#include <vector>

#include "include/dart_api.h"
#include "include/dart_embedder_api.h"

#include "bin/dartutils.h"

#include "def.h"

namespace {
bool ReadFile(const char* path, std::vector<char>& buf) {
  std::ifstream file(path, std::ios::binary | std::ios::ate);
  if (!file) {
    return false;
  }

  std::streamsize size = file.tellg();
  file.seekg(0, std::ios::beg);

  buf.resize(size);
  return !file.read(buf.data(), size).fail();
}

#define ABORT_IF_ERROR(e) AbortIfError((e), #e)
#define ABORT_IF_ERROR_OR_NULL(e) AbortIfErrorOrNull((e), #e)

const char* ToCString(Dart_Handle handle) {
  if (Dart_IsError(handle)) {
    return Dart_GetError(handle);
  } else if (Dart_IsString(handle)) {
    const char* result = nullptr;
    Dart_Handle err = Dart_StringToCString(handle, &result);
    if (Dart_IsError(err)) {
      return Dart_GetError(err);
    } else {
      return result;
    }
  } else {
    return ToCString(Dart_ToString(handle));
  }
}

Dart_Handle AbortIfError(Dart_Handle result, const char* action) {
  if (Dart_IsError(result)) {
    std::cerr << action << " failed with error: " << ToCString(result)
              << std::endl;
    abort();
  }
  return result;
}

Dart_Handle AbortIfErrorOrNull(Dart_Handle result, const char* action) {
  if (Dart_IsNull(AbortIfError(result, action))) {
    std::cerr << action << " returned null" << std::endl;
    abort();
  }
  return result;
}

Dart_Handle NewString(const char* str) {
  return ABORT_IF_ERROR(Dart_NewStringFromCString(str));
}

}  // namespace

// Linked snapshots provide fast way to spawn new isolates.
// Important: if when spawning isolate from core snapshot you need to
// pass VmSnapshot to Dart_Initialize() via vm_snapshot_data and
// vm_snapshot_instructions parameters.
extern "C" {
extern const uint8_t kDartVmSnapshotData[];
extern const uint8_t kDartVmSnapshotInstructions[];
extern const uint8_t kDartCoreIsolateSnapshotData[];
extern const uint8_t kDartCoreIsolateSnapshotInstructions[];
}

// This is almost the minimal example of Dart runtime embedding. In this example
// we don't start either kernel-service or vm-service isolates and don't use
// kernel platform or core snapshot to initialize the isolate, instead we
// expect fully linked kernel program as input.
//
//   $ ninja -C out/ReleaseX64 embedder_example_2
//   $ cat /tmp/hello.dart
//   import 'dart:async';
//
//   void main() {
//     print("Hello, World!");
//     var count = 0;
//     Timer.periodic(Duration(seconds: 1), (timer) {
//       print('${++count} second${count > 1 ? 's' : ''} passed');
//       if (count > 5) {
//         timer.cancel();
//       }
//     });
//   }
//   $ dart pkg/vm/bin/gen_kernel.dart --platform out/ReleaseX64/vm_platform_strong.dill -o /tmp/hello.dill /tmp/hello.dart
//   $ out/ReleaseX64/embedder_example_2 /tmp/hello.dill
//   Hello, World!
//   1 second passed
//   2 seconds passed
//   3 seconds passed
//   4 seconds passed
//   5 seconds passed
//   6 seconds passed
//
int DEF_RunKernel(const char *kernel_binary_path) {
  char* error = nullptr;
  if (!dart::embedder::InitOnce(&error)) {
    std::cerr << "Standalone embedder initialization failed: " << error
              << std::endl;
    free(error);
    abort();
  }

  std::vector<const char*> flags{};
  error = Dart_SetVMFlags(flags.size(), flags.data());
  if (error != nullptr) {
    std::cerr << "Dart_SetVMFlags failed: " << error << std::endl;
    abort();
  }

  Dart_InitializeParams init_params;
  memset(&init_params, 0, sizeof(init_params));
  init_params.vm_snapshot_data = kDartVmSnapshotData;
  init_params.vm_snapshot_instructions = kDartVmSnapshotInstructions;
  init_params.version = DART_INITIALIZE_PARAMS_CURRENT_VERSION;

  error = Dart_Initialize(&init_params);
  if (error != nullptr) {
    dart::embedder::Cleanup();
    std::cerr << "Dart_Initialize failed: " << error << std::endl;
    free(error);
    abort();
  }

  std::vector<char> kernel_buffer;
  if (!ReadFile(kernel_binary_path, kernel_buffer)) {
    std::cerr << "Failed to read " << kernel_binary_path << std::endl;
    abort();
  }

  // Ready to create and run isolates here.
  Dart_Isolate isolate = Dart_CreateIsolateGroup(
      /*script_uri=*/kernel_binary_path,
      /*name=*/"main",
      /*isolate_snapshot_data=*/kDartCoreIsolateSnapshotData,
      /*isolate_snapshot_instructions=*/kDartCoreIsolateSnapshotInstructions,
      /*flags=*/nullptr,
      /*isolate_group_data=*/nullptr,
      /*isolate_data=*/nullptr, &error);

  if (isolate == nullptr) {
    std::cerr << "Failed to create an isolate: " << error << std::endl;
    abort();
  }

  Dart_EnterScope();

  // Initialize core libraries.
  ABORT_IF_ERROR(dart::bin::DartUtils::PrepareForScriptLoading(
      /*is_service_isolate=*/false, /*trace_loading=*/false));

  // Dart_CreateIsolateGroupFromKernel currently does not properly set the root
  // library (one that contains main entry point) so we are just supplying
  // it from the command line.
  Dart_Handle main_library = ABORT_IF_ERROR_OR_NULL(Dart_LoadLibraryFromKernel(
      reinterpret_cast<uint8_t*>(kernel_buffer.data()), kernel_buffer.size()));
  ABORT_IF_ERROR(Dart_SetRootLibrary(main_library));

  // Have a main isolate ready to go - we are in it after Dart_CreateIsolate*.
  Dart_Handle root_library = ABORT_IF_ERROR_OR_NULL(Dart_RootLibrary());

  ABORT_IF_ERROR(Dart_Invoke(root_library, NewString("main"), 0, nullptr));
  ABORT_IF_ERROR(Dart_RunLoop());

  Dart_ExitScope();
  Dart_ShutdownIsolate();

  error = Dart_Cleanup();
  if (error != nullptr) {
    std::cerr << "Dart_Cleanup failed: " << error << std::endl;
    free(error);
  }
  dart::embedder::Cleanup();

  return 0;
}

