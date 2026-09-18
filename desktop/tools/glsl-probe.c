/*
 * Compile a GLSL ES fragment shader in a real driver, and optionally evaluate
 * it, so the result can be checked against something.
 *
 *     glsl-probe --compile <frag>
 *     glsl-probe --eval <frag> <width> <height> <out.raw> [name=value ...]
 *
 * A uniform given as "sampler=r,g,b,a" is not set as a uniform: it binds a 1x1
 * texture of that colour to texture unit 0. Sampling an unbound sampler is
 * undefined, so a shader that reads its window texture has to be given one for
 * the numbers coming back to mean anything.
 *
 * WHY A C PROGRAM AND NOT A PYTHON BINDING
 *
 * KWin compiles its shaders as "#version 300 es" -- GLSL ES 3.00 -- and the
 * Python GL bindings available offline give a desktop OpenGL core context,
 * which rejects that version outright. Compiling the shader under a language
 * the compositor does not use would prove nothing. This gets a real GLES 3
 * context from Mesa (llvmpipe is fine; the compiler is the same one) and
 * compiles exactly what KWin would hand the driver.
 *
 * --eval renders a full-viewport quad into an RGBA32F framebuffer and writes
 * the raw floats, so the shader's output can be compared numerically against
 * another implementation of the same maths rather than eyeballed.
 *
 *     cc -O2 -o glsl-probe glsl-probe.c -lEGL -lGLESv2
 *
 * Exit status is 0 on success; a compile failure prints the driver's log and
 * exits 1, which is the point.
 */

#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl3.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *VERT_SRC =
    "#version 300 es\n"
    "precision highp float;\n"
    "in vec4 position;\n"
    "out vec2 texcoord0;\n"
    "out vec2 position0;\n"
    "uniform vec2 probe_size;\n"
    "uniform vec2 probe_origin;\n"
    "void main() {\n"
    /* A full-viewport quad whose position0 spans 0..size with y DOWNWARD,
     * matching what KWin's base.vert hands a window's fragment shader. */
    "    texcoord0 = position.xy * 0.5 + 0.5;\n"
    /* probe_origin shifts position0 so a grid can straddle the surface edge
     * and reach NEGATIVE coordinates -- which is where a window's shadow sits
     * in KWin, and where an ungated effect misbehaves. Without it the grid is
     * always inside the surface and a boundary guard is never exercised. */
    "    position0 = vec2(texcoord0.x, 1.0 - texcoord0.y) * probe_size - probe_origin;\n"
    "    gl_Position = vec4(position.xy, 0.0, 1.0);\n"
    "}\n";

static char *slurp(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", path); return NULL; }
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = malloc(n + 1);
    if (fread(buf, 1, n, f) != (size_t)n) { fclose(f); free(buf); return NULL; }
    buf[n] = 0;
    fclose(f);
    return buf;
}

static EGLDisplay g_display;

static int gl_init(void)
{
    PFNEGLGETPLATFORMDISPLAYEXTPROC getPlatformDisplay =
        (PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");
    if (!getPlatformDisplay) { fprintf(stderr, "no eglGetPlatformDisplayEXT\n"); return 0; }

    /* Surfaceless: there is no X server or DRM device here, and none is
     * needed -- everything renders to a framebuffer object. */
    g_display = getPlatformDisplay(EGL_PLATFORM_SURFACELESS_MESA, EGL_DEFAULT_DISPLAY, NULL);
    if (g_display == EGL_NO_DISPLAY) { fprintf(stderr, "no surfaceless display\n"); return 0; }

    EGLint maj, min;
    if (!eglInitialize(g_display, &maj, &min)) { fprintf(stderr, "eglInitialize 0x%x\n", eglGetError()); return 0; }

    EGLint cfgattr[] = { EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
                         EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT, EGL_NONE };
    EGLConfig cfg; EGLint n;
    if (!eglChooseConfig(g_display, cfgattr, &cfg, 1, &n) || n < 1) { fprintf(stderr, "no config\n"); return 0; }

    eglBindAPI(EGL_OPENGL_ES_API);
    EGLint ctxattr[] = { EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE };
    EGLContext ctx = eglCreateContext(g_display, cfg, EGL_NO_CONTEXT, ctxattr);
    if (ctx == EGL_NO_CONTEXT) { fprintf(stderr, "no context 0x%x\n", eglGetError()); return 0; }
    if (!eglMakeCurrent(g_display, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx)) {
        fprintf(stderr, "eglMakeCurrent 0x%x\n", eglGetError()); return 0;
    }
    return 1;
}

static GLuint compile(GLenum type, const char *src, const char *what)
{
    GLuint s = glCreateShader(type);
    glShaderSource(s, 1, &src, NULL);
    glCompileShader(s);
    GLint ok = 0;
    glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        GLint len = 0;
        glGetShaderiv(s, GL_INFO_LOG_LENGTH, &len);
        char *log = malloc(len + 1);
        glGetShaderInfoLog(s, len, NULL, log);
        fprintf(stderr, "%s failed to compile:\n%s\n", what, log);
        free(log);
        return 0;
    }
    return s;
}

static GLuint link_program(const char *frag_src)
{
    GLuint vs = compile(GL_VERTEX_SHADER, VERT_SRC, "vertex shader");
    if (!vs) return 0;
    GLuint fs = compile(GL_FRAGMENT_SHADER, frag_src, "fragment shader");
    if (!fs) return 0;

    GLuint p = glCreateProgram();
    glAttachShader(p, vs);
    glAttachShader(p, fs);
    glBindAttribLocation(p, 0, "position");
    glLinkProgram(p);
    GLint ok = 0;
    glGetProgramiv(p, GL_LINK_STATUS, &ok);
    if (!ok) {
        GLint len = 0;
        glGetProgramiv(p, GL_INFO_LOG_LENGTH, &len);
        char *log = malloc(len + 1);
        glGetProgramInfoLog(p, len, NULL, log);
        fprintf(stderr, "program failed to link:\n%s\n", log);
        free(log);
        return 0;
    }
    return p;
}

/* name=v | name=v,v | name=v,v,v | name=v,v,v,v -- enough for the uniforms
 * these shaders take, and it fails loudly rather than guessing. */
static void set_uniform(GLuint prog, const char *arg)
{
    char buf[256];
    strncpy(buf, arg, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = 0;
    char *eq = strchr(buf, '=');
    if (!eq) { fprintf(stderr, "bad uniform '%s', want name=value\n", arg); exit(2); }
    *eq = 0;
    if (strcmp(buf, "sampler") == 0) {
        /* A 1x1 texture of the given colour, so texture() returns a known
         * value instead of whatever an unbound sampler happens to yield. */
        float c[4] = {0, 0, 0, 0};
        int m = 0;
        for (char *tok = strtok(eq + 1, ","); tok && m < 4; tok = strtok(NULL, ","))
            c[m++] = (float)atof(tok);
        GLuint t;
        glGenTextures(1, &t);
        glActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, t);
        glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA32F, 1, 1);
        glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, 1, 1, GL_RGBA, GL_FLOAT, c);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
        GLint sloc = glGetUniformLocation(prog, "sampler");
        if (sloc >= 0) glUniform1i(sloc, 0);
        return;
    }
    GLint loc = glGetUniformLocation(prog, buf);
    if (loc < 0) {
        /* Not an error: a uniform the compiler removed as unused is normal,
         * and pretending otherwise would make this tool reject valid shaders. */
        return;
    }
    float v[4] = {0, 0, 0, 0};
    int n = 0;
    for (char *tok = strtok(eq + 1, ","); tok && n < 4; tok = strtok(NULL, ","))
        v[n++] = (float)atof(tok);
    switch (n) {
    case 1: glUniform1f(loc, v[0]); break;
    case 2: glUniform2f(loc, v[0], v[1]); break;
    case 3: glUniform3f(loc, v[0], v[1], v[2]); break;
    case 4: glUniform4f(loc, v[0], v[1], v[2], v[3]); break;
    default: fprintf(stderr, "bad uniform '%s'\n", arg); exit(2);
    }
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: glsl-probe --compile <frag>\n"
                        "       glsl-probe --eval <frag> <w> <h> <out.raw> [name=value ...]\n");
        return 2;
    }
    const int eval = strcmp(argv[1], "--eval") == 0;
    char *frag = slurp(argv[2]);
    if (!frag) return 2;

    if (!gl_init()) return 2;

    GLuint prog = link_program(frag);
    if (!prog) return 1;

    if (!eval) {
        printf("ok: compiles and links on %s\n", glGetString(GL_RENDERER));
        return 0;
    }
    if (argc < 6) { fprintf(stderr, "--eval needs <w> <h> <out.raw>\n"); return 2; }
    const int w = atoi(argv[3]), h = atoi(argv[4]);
    const char *out_path = argv[5];

    /* RGBA32F, so the comparison is against the shader's actual arithmetic
     * rather than against 8-bit quantisation of it. */
    GLuint tex;
    glGenTextures(1, &tex);
    glBindTexture(GL_TEXTURE_2D, tex);
    glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA32F, w, h);

    GLuint fbo;
    glGenFramebuffers(1, &fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
        fprintf(stderr, "framebuffer incomplete\n"); return 2;
    }

    glViewport(0, 0, w, h);
    glUseProgram(prog);
    glUniform2f(glGetUniformLocation(prog, "probe_size"), (float)w, (float)h);
    glUniform2f(glGetUniformLocation(prog, "probe_origin"), 0.0f, 0.0f);
    for (int i = 6; i < argc; i++) set_uniform(prog, argv[i]);

    const float quad[] = { -1, -1, 1, -1, -1, 1, 1, 1 };
    GLuint vao, vbo;
    glGenVertexArrays(1, &vao);
    glBindVertexArray(vao);
    glGenBuffers(1, &vbo);
    glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glBufferData(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_STATIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, 0);

    glDisable(GL_BLEND);
    glClearColor(0, 0, 0, 0);
    glClear(GL_COLOR_BUFFER_BIT);
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    glFinish();

    float *pix = malloc((size_t)w * h * 4 * sizeof(float));
    glReadPixels(0, 0, w, h, GL_RGBA, GL_FLOAT, pix);
    GLenum err = glGetError();
    if (err != GL_NO_ERROR) { fprintf(stderr, "GL error 0x%x\n", err); return 2; }

    FILE *f = fopen(out_path, "wb");
    if (!f) { fprintf(stderr, "cannot write %s\n", out_path); return 2; }
    /* Row 0 is the BOTTOM in GL. Write top-down so the caller gets the same
     * orientation the shader was given, rather than a silently mirrored
     * image that would make a y-dependent effect look symmetric. */
    for (int y = h - 1; y >= 0; y--)
        fwrite(pix + (size_t)y * w * 4, sizeof(float), (size_t)w * 4, f);
    fclose(f);
    printf("ok: evaluated %dx%d on %s\n", w, h, glGetString(GL_RENDERER));
    return 0;
}
