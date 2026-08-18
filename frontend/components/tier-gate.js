/**
 * نظام إدارة الخطط (Tier Gate) — يتحكم في الوصول للمميزات على الواجهة.
 *
 * يستخدم localStorage لتتبع الاستخدام اليومي، ويوفر واجهة للتحقق
 * من المميزات قبل تنفيذها.
 *
 * الاستخدام:
 *   import { TierGate } from './components/tier-gate.js';
 *   const gate = new TierGate();
 *
 *   if (!gate.canSearch()) {
 *       showUpgradeModal(gate.getUpgradePrompt('search'));
 *       return;
 *   }
 *
 *   gate.recordSearch();
 *   // ... execute search
 */
class TierGate {
    constructor() {
        this.tier = this._loadTier();
        this.usage = this._loadUsage();
    }

    // ─── إدارة الخطة ───

    /** تحميل الخطة الحالية من localStorage */
    _loadTier() {
        try {
            return localStorage.getItem('alforaij_tier') || 'free';
        } catch {
            return 'free';
        }
    }

    /** حفظ الخطة الحالية */
    setTier(tier) {
        this.tier = tier;
        try {
            localStorage.setItem('alforaij_tier', tier);
        } catch { /* storage full or unavailable */ }
    }

    /** الحصول على الخطة الحالية */
    getTier() {
        return this.tier;
    }

    // ─── إدارة الاستخدام ───

    /** تحميل سجل الاستخدام اليومي */
    _loadUsage() {
        try {
            const raw = localStorage.getItem('alforaij_usage');
            if (!raw) return this._emptyUsage();
            const data = JSON.parse(raw);
            // إعادة تعييد العداد إذا كان التاريخ مختلفاً
            if (data.date !== this._today()) {
                return this._emptyUsage();
            }
            return data;
        } catch {
            return this._emptyUsage();
        }
    }

    /** هيكل استخدام فارغ */
    _emptyUsage() {
        return { date: this._today(), searches: 0, pdfs: 0, alerts: 0 };
    }

    /** حفظ سجل الاستخدام */
    _saveUsage() {
        try {
            localStorage.setItem('alforaij_usage', JSON.stringify(this.usage));
        } catch { /* storage full or unavailable */ }
    }

    /** التاريخ اليومي (YYYY-MM-DD) */
    _today() {
        return new Date().toISOString().split('T')[0];
    }

    // ─── حدود الخطط ───

    /** حدود كل خطة */
    getLimits() {
        return {
            free: { searches: 10, comparisons: 3, pdfs: 0, alerts: 0 },
            pro: { searches: Infinity, comparisons: Infinity, pdfs: Infinity, alerts: Infinity },
            enterprise: { searches: Infinity, comparisons: Infinity, pdfs: Infinity, alerts: Infinity },
        }[this.tier] || { searches: 0, comparisons: 0, pdfs: 0, alerts: 0 };
    }

    // ─── فحص المميزات ───

    /** هل يمكنه البحث؟ */
    canSearch() {
        const limits = this.getLimits();
        return this.usage.searches < limits.searches;
    }

    /** هل يمكنه إنشاء PDF؟ */
    canGeneratePdf() {
        const limits = this.getLimits();
        return limits.pdfs > 0;
    }

    /** هل يمكنه تفعيل التنبيهات؟ */
    canUseAlerts() {
        const limits = this.getLimits();
        return limits.alerts > 0 || this.tier !== 'free';
    }

    /** هل يمكنه الوصول للبيانات الرسمية؟ */
    canUseOfficialData() {
        return this.tier === 'pro' || this.tier === 'enterprise';
    }

    /** هل يمكنه استخدام API؟ */
    canUseApi() {
        return this.tier === 'enterprise';
    }

    /** هل يمكنه حفظ التقارير في السحابة؟ */
    canUseCloudStorage() {
        return this.tier === 'pro' || this.tier === 'enterprise';
    }

    // ─── تسجيل الاستخدام ───

    /** تسجيل عملية بحث */
    recordSearch() {
        this.usage.searches += 1;
        this._saveUsage();
    }

    /** تسجيل إنشاء PDF */
    recordPdf() {
        this.usage.pdfs += 1;
        this._saveUsage();
    }

    /** تسجيل تنبيه */
    recordAlert() {
        this.usage.alerts += 1;
        this._saveUsage();
    }

    // ─── معلومات الاستخدام ───

    /** الحصول على معلومات الاستخدام الحالية */
    getUsageInfo() {
        const limits = this.getLimits();
        return {
            tier: this.tier,
            searches: {
                used: this.usage.searches,
                limit: limits.searches,
                remaining: limits.searches === Infinity ? Infinity : Math.max(0, limits.searches - this.usage.searches),
            },
            pdfs: {
                used: this.usage.pdfs,
                limit: limits.pdfs,
            },
            alerts: {
                used: this.usage.alerts,
                limit: limits.alerts,
            },
        };
    }

    // ─── رسالة الترقية ───

    /** الحصول على رسالة ترقية مناسبة */
    getUpgradePrompt(feature) {
        const prompts = {
            search: {
                title: 'وصلت الحد اليومي',
                message: 'لقد استنفدت عمليات البحث اليومية (10بحث). رقّ خطتك للحصول على بحث غير محدود.',
                cta: 'رقّ إلى المحترف',
                price: '15 د.ك/شهر',
            },
            pdf_reports: {
                title: 'PDF متاح فقط للمحترفين',
                message: 'تقارير PDF الاحترافية متاحة في الخطة المحترفة. ابدأ الآن واحصل على تقارير جاهزة للعميل.',
                cta: 'ابدأ المحترف',
                price: '15 د.ك/شهر',
            },
            opportunity_alerts: {
                title: 'تنبيهات الفرص للمحترفين',
                message: 'تنبيهات الفرص اليومية عبر واتساب متاحة في الخطة المحترفة.',
                cta: 'فعّل التنبيهات',
                price: '15 د.ك/شهر',
            },
            official_data: {
                title: 'بيانات رسمية للمحترفين',
                message: 'المقارنات الرسمية والصفقات الموثقة متاحة في الخطة المحترفة.',
                cta: 'افتح البيانات الرسمية',
                price: '15 د.ك/شهر',
            },
            api_access: {
                title: 'API للمؤسسات',
                message: 'API الوصول متاح فقط في الخطة المؤسسية.',
                cta: 'تواصل معنا',
                price: 'مخصص',
            },
        };

        return prompts[feature] || {
            title: 'ميزة متقدمة',
            message: 'هذه الميزة متاحة في الخطة الأعلى.',
            cta: 'ترقّ الآن',
            price: '',
        };
    }

    // ─── واجهة عرض ───

    /** إنشاء شريط استخدام для العرض */
    createUsageBar() {
        const info = this.getUsageInfo();
        if (info.searches.limit === Infinity) return null;

        const pct = Math.min(100, (info.searches.used / info.searches.limit) * 100);
        const isWarning = pct >= 80;
        const isDanger = pct >= 100;

        return {
            used: info.searches.used,
            limit: info.searches.limit,
            remaining: info.searches.remaining,
            percentage: pct,
            isWarning,
            isDanger,
            message: isDanger
                ? 'وصلت الحد الأقصى — رقّ خطتك'
                : isWarning
                ? `متبقي ${info.searches.remaining} فقط`
                : `${info.searches.remaining} من ${info.searches.limit} متبقي`,
        };
    }
}

// تصدير للاستخدام作为模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TierGate;
}

// تصدير للنافذة للاستخدام المباشر
if (typeof window !== 'undefined') {
    window.TierGate = TierGate;
}
