/* Links zlib so the dependency detector has a library besides libc to name. */
#include <stdio.h>
#include <zlib.h>

int main(void)
{
    printf("hello, zlib %s\n", zlibVersion());
    return 0;
}
