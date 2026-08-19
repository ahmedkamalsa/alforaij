"""
نظام التصنيفات الذكية للإعلانات العقارية
AI-Powered Listing Classification System

يمكن التصنيف التلقائي للإعلانات باستخدام بيانات وصفية منظمة:
- نوع العقار (سكني، تجاري، أرض، إداري)
- مستوى الاستثمار (ممتاز، جيد، متوسط، ضعيف)
- الأولوية (عالية، متوسطة، منخفضة)
- الحساسية (عامة، حساسة، سرية)
- القسم (بيع، إيجار، استثمار، تقييم)
- حالة الإعلان (نشط، منتهي، معلق)
- نوع المعاملة (مباشر، مكتب، وسيط)
- مصدر البيانات (محلي، خارجي، مختلط)
- مستوى الثقة (عالي، متوسط، منخفض)
- الفئة المستهدفة (مستثمر، مشتري، مستأجر، وسيط)
"""

import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime


class ClassificationCategory(Enum):
    """فئات التصنيف الأساسية"""
    PROPERTY_TYPE = "property_type"          # نوع العقار
    INVESTMENT_LEVEL = "investment_level"    # مستوى الاستثمار
    PRIORITY = "priority"                    # الأولوية
    SENSITIVITY = "sensitivity"              # الحساسية
    DEPARTMENT = "department"                # القسم
    STATUS = "status"                        # حالة الإعلان
    DEAL_TYPE = "deal_type"                  # نوع المعاملة
    DATA_SOURCE = "data_source"              # مصدر البيانات
    TRUST_LEVEL = "trust_level"              # مستوى الثقة
    TARGET_AUDIENCE = "target_audience"      # الفئة المستهدفة


@dataclass
class Classifier:
    """مصنف واحد"""
    id: str
    name: str
    name_en: str
    category: ClassificationCategory
    description: str
    values: List[str]
    is_active: bool = True
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


@dataclass
class ClassificationResult:
    """نتيجة التصنيف"""
    listing_id: str
    classifier_id: str
    value: str
    confidence: float  # 0.0 - 1.0
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class ListingClassification:
    """تصنيف كامل لإعلان"""
    listing_id: str
    classifications: Dict[str, str]  # classifier_id -> value
    scores: Dict[str, float]  # classifier_id -> confidence
    overall_score: float = 0.0
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.scores:
            self.overall_score = sum(self.scores.values()) / len(self.scores)


class ListingClassifier:
    """نظام التصنيف الرئيسي"""
    
    def __init__(self):
        self.classifiers: Dict[str, Classifier] = {}
        self.classifications: Dict[str, ListingClassification] = {}
        self._init_default_classifiers()
    
    def _init_default_classifiers(self):
        """تهيئة المصنفات الافتراضية"""
        defaults = [
            Classifier(
                id="property_type",
                name="نوع العقار",
                name_en="Property Type",
                category=ClassificationCategory.PROPERTY_TYPE,
                description="تصنيف حسب نوع العقار",
                values=["بيت", "شقة", "أرض", "مكتب", "محل", "مستودع", "فيلا", "دوبلكس"]
            ),
            Classifier(
                id="investment_level",
                name="مستوى الاستثمار",
                name_en="Investment Level",
                category=ClassificationCategory.INVESTMENT_LEVEL,
                description="تقييم فرصة الاستثمار",
                values=["ممتاز", "جيد جداً", "جيد", "متوسط", "ضعيف"]
            ),
            Classifier(
                id="priority",
                name="الأولوية",
                name_en="Priority",
                category=ClassificationCategory.PRIORITY,
                description="أولوية الإعلان",
                values=["عالية", "متوسطة", "منخفضة"]
            ),
            Classifier(
                id="deal_type",
                name="نوع المعاملة",
                name_en="Deal Type",
                category=ClassificationCategory.DEAL_TYPE,
                description="نوع المعاملة العقارية",
                values=["بيع مباشر", "إيجار مباشر", "مكتب عقاري", "وسيط", "مزاد"]
            ),
            Classifier(
                id="data_source",
                name="مصدر البيانات",
                name_en="Data Source",
                category=ClassificationCategory.DATA_SOURCE,
                description="مصدر بيانات الإعلان",
                values=["الفريج", "OpenSooq", "Mourjan", "Q8Aqar", "4Sale", "Waseet", "الحسبة", "Sakan", "مختلط"]
            ),
            Classifier(
                id="trust_level",
                name="مستوى الثقة",
                name_en="Trust Level",
                category=ClassificationCategory.TRUST_LEVEL,
                description="مستوى ثقة البيانات",
                values=["عالي", "متوسط", "منخفض"]
            ),
            Classifier(
                id="target_audience",
                name="الفئة المستهدفة",
                name_en="Target Audience",
                category=ClassificationCategory.TARGET_AUDIENCE,
                description="الفئة المستهدفة من الإعلان",
                values=["مستثمر", "مشتري", "مستأجر", "وسيط", "مطور"]
            ),
        ]
        
        for classifier in defaults:
            self.classifiers[classifier.id] = classifier
    
    def add_classifier(self, classifier: Classifier) -> bool:
        """إضافة مصنف جديد"""
        if len(self.classifiers) >= 10:
            return False  # الحد الأقصى 10 مصنفات
        self.classifiers[classifier.id] = classifier
        return True
    
    def remove_classifier(self, classifier_id: str) -> bool:
        """حذف مصنف"""
        if classifier_id in self.classifiers:
            del self.classifiers[classifier_id]
            return True
        return False
    
    def get_classifiers(self) -> List[Dict]:
        """جلب جميع المصنفات"""
        return [asdict(c) for c in self.classifiers.values()]
    
    def classify_listing(self, listing: Dict) -> ListingClassification:
        """تصنيف إعلان واحد"""
        listing_id = listing.get("id", str(hash(json.dumps(listing, default=str))))
        classifications = {}
        scores = {}
        
        # تصنيف نوع العقار
        prop_type = self._classify_property_type(listing)
        classifications["property_type"] = prop_type
        scores["property_type"] = 0.9
        
        # تصنيف مستوى الاستثمار
        inv_level = self._classify_investment_level(listing)
        classifications["investment_level"] = inv_level
        scores["investment_level"] = 0.85
        
        # تصنيف الأولوية
        priority = self._classify_priority(listing)
        classifications["priority"] = priority
        scores["priority"] = 0.8
        
        # تصنيف نوع المعاملة
        deal_type = self._classify_deal_type(listing)
        classifications["deal_type"] = deal_type
        scores["deal_type"] = 0.95
        
        # تصنيف مصدر البيانات
        source = self._classify_data_source(listing)
        classifications["data_source"] = source
        scores["data_source"] = 1.0
        
        # تصنيف مستوى الثقة
        trust = self._classify_trust_level(listing)
        classifications["trust_level"] = trust
        scores["trust_level"] = 0.75
        
        # تصنيف الفئة المستهدفة
        audience = self._classify_target_audience(listing)
        classifications["target_audience"] = audience
        scores["target_audience"] = 0.7
        
        # إنشاء التصنيف
        result = ListingClassification(
            listing_id=listing_id,
            classifications=classifications,
            scores=scores,
            tags=self._generate_tags(classifications)
        )
        
        self.classifications[listing_id] = result
        return result
    
    def _classify_property_type(self, listing: Dict) -> str:
        """تصنيف نوع العقار"""
        title = (listing.get("title", "") + " " + listing.get("description", "")).lower()
        property_type = listing.get("propertyType", "").lower()
        
        if any(w in title for w in ["شقة", "شُقة", "appartement"]):
            return "شقة"
        elif any(w in title for w in ["أرض", "ارض", "land"]):
            return "أرض"
        elif any(w in title for w in ["مكتب", "مكتبي", "office"]):
            return "مكتب"
        elif any(w in title for w in ["محل", "محلات", "shop"]):
            return "محل"
        elif any(w in title for w in ["فيلا", "vila"]):
            return "فيلا"
        elif any(w in title for w in ["دوبلكس", "duplex"]):
            return "دوبلكس"
        elif any(w in title for w in ["مستودع", "warehouse"]):
            return "مستودع"
        elif "بيت" in property_type or "house" in property_type:
            return "بيت"
        else:
            return "بيت"  # الافتراضي
    
    def _classify_investment_level(self, listing: Dict) -> str:
        """تصنيف مستوى الاستثمار"""
        score = listing.get("opportunityScore", 0)
        price = listing.get("price", 0)
        space = listing.get("space", 0)
        
        if score > 80:
            return "ممتاز"
        elif score > 60:
            return "جيد جداً"
        elif score > 40:
            return "جيد"
        elif score > 20:
            return "متوسط"
        else:
            return "ضعيف"
    
    def _classify_priority(self, listing: Dict) -> str:
        """تصنيف الأولوية"""
        score = listing.get("opportunityScore", 0)
        movement = listing.get("movement", 0)
        
        if score > 70 or movement > 5:
            return "عالية"
        elif score > 40 or movement > 2:
            return "متوسطة"
        else:
            return "منخفضة"
    
    def _classify_deal_type(self, listing: Dict) -> str:
        """تصنيف نوع المعاملة"""
        tx = listing.get("transaction", "").lower()
        listing_mode = listing.get("listingMode", "").lower()
        
        if "بيع" in tx or "sell" in tx:
            if "مكتب" in listing_mode or "office" in listing_mode:
                return "مكتب عقاري"
            return "بيع مباشر"
        elif "إيجار" in tx or "rent" in tx:
            if "مكتب" in listing_mode or "office" in listing_mode:
                return "مكتب عقاري"
            return "إيجار مباشر"
        elif "وسيط" in listing_mode:
            return "وسيط"
        else:
            return "بيع مباشر"
    
    def _classify_data_source(self, listing: Dict) -> str:
        """تصنيف مصدر البيانات"""
        source = listing.get("source", "").lower()
        
        source_map = {
            "الفريج": "الفريج",
            "alforaij": "الفريج",
            "opensooq": "OpenSooq",
            "mourjan": "Mourjan",
            "q8aqar": "Q8Aqar",
            "4sale": "4Sale",
            "waseet": "Waseet",
            "الحسبة": "الحسبة",
            "sakan": "Sakan"
        }
        
        for key, value in source_map.items():
            if key in source:
                return value
        
        return "مختلط"
    
    def _classify_trust_level(self, listing: Dict) -> str:
        """تصنيف مستوى الثقة"""
        has_price = listing.get("price", 0) > 0
        has_space = listing.get("space", 0) > 0
        has_evidence = listing.get("evidenceCount", 0) > 0
        source = listing.get("source", "")
        
        trust_score = 0
        if has_price: trust_score += 30
        if has_space: trust_score += 30
        if has_evidence: trust_score += 25
        if "الفريج" in source: trust_score += 15
        
        if trust_score >= 70:
            return "عالي"
        elif trust_score >= 40:
            return "متوسط"
        else:
            return "منخفض"
    
    def _classify_target_audience(self, listing: Dict) -> str:
        """تصنيف الفئة المستهدفة"""
        tx = listing.get("transaction", "").lower()
        score = listing.get("opportunityScore", 0)
        
        if "إيجار" in tx:
            return "مستثمر"
        elif score > 60:
            return "مستثمر"
        elif "شراء" in tx or "بيع" in tx:
            return "مشتري"
        else:
            return "مستثمر"
    
    def _generate_tags(self, classifications: Dict) -> List[str]:
        """إنشاء وسوم من التصنيفات"""
        tags = []
        
        if classifications.get("investment_level") in ["ممتاز", "جيد جداً"]:
            tags.append("فرصة مميزة")
        
        if classifications.get("priority") == "عالية":
            tags.append("أولوية عالية")
        
        if classifications.get("trust_level") == "عالي":
            tags.append("بيانات موثوقة")
        
        if classifications.get("target_audience") == "مستثمر":
            tags.append("مناسب للمستثمرين")
        
        return tags
    
    def classify_batch(self, listings: List[Dict]) -> List[ListingClassification]:
        """تصنيف مجموعة إعلانات"""
        return [self.classify_listing(listing) for listing in listings]
    
    def get_statistics(self) -> Dict:
        """إحصائيات التصنيف"""
        if not self.classifications:
            return {"total": 0}
        
        stats = {
            "total": len(self.classifications),
            "by_property_type": {},
            "by_investment_level": {},
            "by_priority": {},
            "by_deal_type": {},
            "by_source": {},
            "by_trust_level": {},
            "by_audience": {},
            "average_score": 0
        }
        
        total_score = 0
        for classification in self.classifications.values():
            # عدد حسب نوع العقار
            pt = classification.classifications.get("property_type", "غير محدد")
            stats["by_property_type"][pt] = stats["by_property_type"].get(pt, 0) + 1
            
            # عدد حسب مستوى الاستثمار
            il = classification.classifications.get("investment_level", "غير محدد")
            stats["by_investment_level"][il] = stats["by_investment_level"].get(il, 0) + 1
            
            # عدد حسب الأولوية
            pr = classification.classifications.get("priority", "غير محدد")
            stats["by_priority"][pr] = stats["by_priority"].get(pr, 0) + 1
            
            # عدد حسب نوع المعاملة
            dt = classification.classifications.get("deal_type", "غير محدد")
            stats["by_deal_type"][dt] = stats["by_deal_type"].get(dt, 0) + 1
            
            # عدد حسب المصدر
            ds = classification.classifications.get("data_source", "غير محدد")
            stats["by_source"][ds] = stats["by_source"].get(ds, 0) + 1
            
            # عدد حسب مستوى الثقة
            tl = classification.classifications.get("trust_level", "غير محدد")
            stats["by_trust_level"][tl] = stats["by_trust_level"].get(tl, 0) + 1
            
            # عدد حسب الفئة المستهدفة
            ta = classification.classifications.get("target_audience", "غير محدد")
            stats["by_audience"][ta] = stats["by_audience"].get(ta, 0) + 1
            
            total_score += classification.overall_score
        
        stats["average_score"] = round(total_score / len(self.classifications), 2)
        
        return stats
    
    def export_classifications(self) -> List[Dict]:
        """تصدير جميع التصنيفات"""
        return [asdict(c) for c in self.classifications.values()]


# نسخة واحدة مشتركة
_classifier_instance = None

def get_classifier() -> ListingClassifier:
    """الحصول على نسخة واحدة من المصنف"""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = ListingClassifier()
    return _classifier_instance
