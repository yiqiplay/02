package com.mediaconv.app;

import android.content.Context;
import android.util.AttributeSet;
import android.util.Log;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.widget.ScrollView;
import android.widget.Scroller;

/**
 * 明确接管触控的滚动容器。
 *
 * 为什么不用原生 ScrollView 的默认行为：
 * 它的 onInterceptTouchEvent 依赖 mIsBeingDragged / mLastMotionY 等内部状态，
 * 这些状态在"纯代码构建视图"的路径上与 XML 加载路径的初始化时机并不完全一致，
 * 实测在本程序里导致手指拖动没有任何响应。
 *
 * 这里自己处理：
 *   - ACTION_DOWN 记录起点
 *   - ACTION_MOVE 一旦超过 touchSlop 就接管手势并直接 scrollBy（不再依赖系统拦截）
 *   - ACTION_UP 根据速度用 Scroller 做惯性滑动
 * 只使用平台 API，不引入任何依赖。
 */
public class DragScrollView extends ScrollView {

    private static final String TAG = "DragScrollView";

    private final int touchSlop;
    private final int minFlingVelocity;
    private final int maxFlingVelocity;
    private final Scroller scroller;

    private float lastY;
    private boolean dragging;
    private boolean startFromTop;   // 按下时是否已经在顶部（用于下拉回弹判断）

    public DragScrollView(Context context) {
        this(context, null);
    }

    public DragScrollView(Context context, AttributeSet attrs) {
        super(context, attrs);
        ViewConfiguration vc = ViewConfiguration.get(context);
        touchSlop = vc.getScaledTouchSlop();
        minFlingVelocity = vc.getScaledMinimumFlingVelocity();
        maxFlingVelocity = vc.getScaledMaximumFlingVelocity();
        scroller = new Scroller(context);
        setVerticalScrollBarEnabled(true);
        setFillViewport(true);
        setOverScrollMode(View.OVER_SCROLL_ALWAYS);
        setFocusable(true);
        setFocusableInTouchMode(true);
    }

    // ---------------------------------------------------------------- 触控

    @Override
    public boolean onInterceptTouchEvent(MotionEvent ev) {
        final int action = ev.getActionMasked();
        switch (action) {
            case MotionEvent.ACTION_DOWN:
                lastY = ev.getY();
                dragging = false;
                startFromTop = getScrollY() <= 0;
                // 让父类也记录一份状态，保持行为一致
                super.onInterceptTouchEvent(ev);
                return false;

            case MotionEvent.ACTION_MOVE: {
                if (dragging) return true;
                float dy = Math.abs(ev.getY() - lastY);
                // 关键：只要竖直位移超过 touchSlop 就接管。
                // 不判断"当前是否还能滚动"，否则滑到边界时手势会被系统抢走。
                if (dy > touchSlop) {
                    dragging = true;
                    lastY = ev.getY();
                    getParent().requestDisallowInterceptTouchEvent(true);
                    // 排错用：确认手势确实被本控件接管了
                    Log.i(TAG, "drag start: scrollY=" + getScrollY()
                            + " content=" + (getChildCount() > 0 ? getChildAt(0).getHeight() : -1)
                            + " viewport=" + getHeight());
                    return true;
                }
                return false;
            }

            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                dragging = false;
                return false;

            default:
                return super.onInterceptTouchEvent(ev);
        }
    }

    @Override
    public boolean onTouchEvent(MotionEvent ev) {
        final int action = ev.getActionMasked();
        switch (action) {
            case MotionEvent.ACTION_DOWN:
                lastY = ev.getY();
                dragging = false;
                startFromTop = getScrollY() <= 0;
                if (!scroller.isFinished()) scroller.abortAnimation();
                // 必须返回 true 才能继续收到后续 MOVE / UP
                return true;

            case MotionEvent.ACTION_MOVE: {
                float y = ev.getY();
                float dy = lastY - y;   // 手指上滑为正 => 内容上滚
                if (!dragging) {
                    if (Math.abs(y - lastY) > touchSlop) {
                        dragging = true;
                        // 减去 slop，避免开始拖动时内容"跳"一下
                        dy = (lastY - y) - Math.signum(lastY - y) * touchSlop;
                        lastY = y;
                    } else {
                        return true;
                    }
                }
                scrollBy(0, Math.round(dy));
                lastY = y;
                return true;
            }

            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL: {
                if (dragging) {
                    float velocity = estimateVelocity(ev);
                    if (Math.abs(velocity) > minFlingVelocity) {
                        if (velocity > maxFlingVelocity) velocity = maxFlingVelocity;
                        if (velocity < -maxFlingVelocity) velocity = -maxFlingVelocity;
                        // fling 的 y 范围给得很宽，越界由 ScrollView 自己钳制在
                        // [0, contentHeight - viewportHeight] 之间，不用我们算。
                        scroller.fling(0, getScrollY(), 0, (int) velocity,
                                0, 0, Integer.MIN_VALUE, Integer.MAX_VALUE);
                        postInvalidateOnAnimation();
                    }
                }
                dragging = false;
                return true;
            }

            default:
                return super.onTouchEvent(ev);
        }
    }

    /** 用 VelocityTracker 估算滑动速度（像素/秒，向上滑为负）。 */
    private float estimateVelocity(MotionEvent ev) {
        android.view.VelocityTracker vt = null;
        try {
            vt = android.view.VelocityTracker.obtain();
            vt.addMovement(ev);
            vt.computeCurrentVelocity(1000, maxFlingVelocity);
            return vt.getYVelocity();
        } catch (Throwable t) {
            return 0;
        } finally {
            if (vt != null) {
                try {
                    vt.recycle();
                } catch (Throwable ignored) {
                }
            }
        }
    }

    // ---------------------------------------------------------------- 惯性滑动

    @Override
    public void computeScroll() {
        if (scroller.computeScrollOffset()) {
            scrollTo(scroller.getCurrX(), scroller.getCurrY());
            postInvalidateOnAnimation();
        }
    }

    // ---------------------------------------------------------------- 诊断

    /** 供外部查询：内容是否真的超出可视区域（用于排错）。 */
    public boolean canScrollContent() {
        if (getChildCount() == 0) return false;
        int content = getChildAt(0).getHeight();
        int viewport = getHeight() - getPaddingTop() - getPaddingBottom();
        return content > viewport;
    }

    /** 打一行状态日志，方便确认布局是否测量正确。 */
    public void logMetrics(String where) {
        if (getChildCount() == 0) {
            Log.i(TAG, where + ": no child yet");
            return;
        }
        int content = getChildAt(0).getHeight();
        int viewport = getHeight() - getPaddingTop() - getPaddingBottom();
        Log.i(TAG, where + ": content=" + content + " viewport=" + viewport
                + " scrollable=" + (content > viewport)
                + " scrollY=" + getScrollY());
    }
}
