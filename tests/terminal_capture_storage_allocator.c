// Faults and counts are enabled only around the operation under test.
#include <stddef.h>

void *__real_malloc(size_t);
void *__real_calloc(size_t, size_t);
void *__real_realloc(void *, size_t);
static int enabled, attempts, failure;

void capture_storage_track(int fail_at) {
    enabled = 1;
    attempts = 0;
    failure = fail_at;
}
int capture_storage_stop(void) {
    enabled = 0;
    return attempts;
}
static int reject(void) {
    return enabled && ++attempts == failure;
}
void *__wrap_malloc(size_t size) {
    return reject() ? NULL : __real_malloc(size);
}
void *__wrap_calloc(size_t count, size_t size) {
    return reject() ? NULL : __real_calloc(count, size);
}
void *__wrap_realloc(void *memory, size_t size) {
    return reject() ? NULL : __real_realloc(memory, size);
}
