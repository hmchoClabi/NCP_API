"""
NCP 플랫폼, 빌링 API 모듈

NCP 상품 가격정보, 사용비용, 할인정보 등을 조회하는 기능을 제공합니다.
"""

from typing import Dict, List, Optional
from utils.common_rest import NCPBaseClient
from ncp_api.base import BaseNCPAPI

class PlatformAPI(BaseNCPAPI):
    
    """
    ================================================================
    LIST PRICE APIs
    ================================================================    
    """ 
    def get_price_list(
        self,
        price_no_list: List[str],
        promise_no_list: Optional[List[str]] = None,
        pay_currency_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        요금제 목록을 조회합니다.
        
        Args:
            price_no_list: 조회할 가격 번호 리스트 (1~99)
            promise_no_list: 약정번호 리스트 (선택사항)
            pay_currency_code: 결제통화코드 (선택사항) (KRW, JPY, USD)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 상품 가격정보 응답 데이터
        """
        params = {}

        for idx, price_no in enumerate(price_no_list, start=1):
            params[f'priceNoList.{idx}'] = price_no

        if promise_no_list is not None:
            for idx, promise_no in enumerate(promise_no_list, start=1):
                params[f'promiseNoList.{idx}'] = promise_no

        if pay_currency_code is not None:
            params['payCurrencyCode'] = pay_currency_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
        
        return self.get('/product/getPriceList', params=params)
    
    def get_product_category_list(
        self,
        product_category_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        상품 카테고리 목록을 조회합니다.
        
        Args:
            product_category_code: 상품 카테고리 코드 (선택사항)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 상품 카테고리 응답 데이터
        """
        params = {}

        if product_category_code is not None:
            params['productCategoryCode'] = product_category_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/product/getProductCategoryList', params=params)   
    
    def get_product_list(
        self,
        region_code: str,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        product_item_kind_code: Optional[str] = None,
        product_category_code: Optional[str] = None,
        product_code: Optional[str] = None,
        product_name: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        상품 목록을 조회합니다.
        
        Args:

            region_code: 지역 코드 (필수항목) getRegionList 로 확인
            page_no: 페이지 번호 (선택사항)
            page_size: 페이지 크기 (선택사항)
            product_item_kind_code: 상품 항목 종류 코드 (선택사항)
            product_category_code: 상품 카테고리 코드 (선택사항)getProductCategoryList로 확인
            product_code: 상품 코드 (선택사항)
            product_name: 상품 이름 (선택사항)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 상품 목록 응답 데이터
        """
        params = {
            'regionCode': region_code
        }
        
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if product_item_kind_code is not None:
            params['productItemKindCode'] = product_item_kind_code
        if product_code is not None:
            params['productCode'] = product_code
        if product_name is not None:
            params['productName'] = product_name
        if product_category_code is not None:
            params['productCategoryCode'] = product_category_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/product/getProductList', params=params)
    
    def get_product_price_list(
        self,
        region_code: str,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        product_item_kind_code: Optional[str] = None,
        product_category_code: Optional[str] = None,
        product_code: Optional[str] = None,
        product_name: Optional[str] = None,
        pay_currency_code: Optional[str] = None,        
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        서비스 및 가격 목록을 조회합니다.
        
        Args:
            region_code: 지역 코드
            product_item_kind_code: 상품 항목 종류 코드 (선택사항)
            product_category_code: 상품 카테고리 코드 (선택사항)
            product_code: 상품 코드 (선택사항)
            product_name: 상품 이름 (선택사항)
            pay_currency_code: 결제통화코드 (선택사항) (KRW, JPY, USD)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 상품 가격 목록 응답 데이터
        """
        params = {
            'regionCode': region_code
            
        }
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if product_item_kind_code is not None:
            params['productItemKindCode'] = product_item_kind_code
        if product_category_code is not None:
            params['productCategoryCode'] = product_category_code
        if product_code is not None:
            params['productCode'] = product_code
        if product_name is not None:
            params['productName'] = product_name
        if pay_currency_code is not None:
            params['payCurrencyCode'] = pay_currency_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
        

        return self.get('/product/getProductPriceList', params=params)
    
    """
    ================================================================
    COST AND USE APIs
    ================================================================    
    """

    def get_contract_demand_cost_list(
        self,
        start_month: str,
        end_month: str,
        page_no : Optional[int] = None,
        page_size : Optional[int] = None,
        is_organization: Optional[bool] = None,
        is_parent: Optional[bool] = None,
        member_no_list: Optional[List[str]] = None,
        contract_no: Optional[str] = None,
        demand_type_code: Optional[str] = None,
        demand_type_detail_code: Optional[str] = None,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        계약별 청구 내역을 조회합니다.
        
        Args:
            start_month: 조회 시작 월 (yyyyMM) 최대 3개월
            end_month: 조회 종료 월 (yyyyMM) 최대 3개월
            is_organization: 조직 고객 여부 (선택사항) (마스터만 사용가능 is_partner와 함께 사용 불가)
            is_parent: 파트너계정 조회 여부 (선택사항) (is_organization과 함께 사용 불가)
            member_no_list: 멤버 번호 리스트 (선택사항) (조직 고객 마스터만 사용가능)
            contract_no: 계약 번호 (선택사항)
            demand_type_code: 청구유형 코드 (선택사항)
            demand_type_detail_code: 청구유형 상세 코드 (선택사항)
            region_code: 지역 코드 (선택사항) getRegionList로 확인
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 계약별 청구 내역 응답 데이터
        """
        params = {
            'startMonth': start_month,
            'endMonth': end_month
        }
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if is_organization and is_parent:
            raise ValueError("is_organization과 is_parent는 함께 사용할 수 없습니다.")
        if is_organization is not None:
            params['isOrganization'] = str(is_organization).lower()
        if is_parent is not None:
            params['isParent'] = str(is_parent).lower()
        if member_no_list is not None:
            params['memberNoList'] = member_no_list
        if contract_no is not None:
            params['contractNo'] = contract_no
        if demand_type_code is not None:
            params['demandTypeCode'] = demand_type_code
        if demand_type_detail_code is not None:
            params['demandTypeDetailCode'] = demand_type_detail_code
        if region_code is not None: 
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
                
        return self.get('/cost/getContractDemandCostList', params=params)
    
    def get_contract_summary_list(
        self,
        contract_month: str,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        is_organization: Optional[bool] = None,
        is_parent: Optional[bool] = None,
        member_no_list: Optional[List[str]] = None,
        contract_type_code: Optional[str] = None,
        contract_status_code: Optional[str] = None,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        사용자 계약 요약 목록을 조회합니다. 계약 요약은 리전 코드, 계약 구분 코드, 계약 수로 구성되어 있습니다.
        
        Args:
            contract_month: 조회할 계약 월 (yyyyMM)
            is_organization: 조직 고객 여부 (선택사항) (마스터만 사용가능 is_partner와 함께 사용 불가)
            is_parent: 파트너계정 조회 여부 (선택사항) (is_organization과 함께 사용 불가)
            member_no_list: 멤버 번호 리스트 (선택사항) (조직 고객 마스터 또는 파트너 대표만 사용가능)
            contract_type_code: 계약 구분 코드 (선택사항)
            contract_status_code: 계약 상태 코드 (선택사항) (ALL, NOML, NLEND)
            region_code: 지역 코드 (선택사항)
        
        Returns:
            Dict: 계약별 요약 내역 응답 데이터
        """
        params = {
            'contractMonth': contract_month
            
        }
        if is_organization and is_parent:
            raise ValueError("is_organization과 is_parent는 함께 사용할 수 없습니다.")
        if is_organization is not None:
            params['isOrganization'] = str(is_organization).lower()
        if is_parent is not None:
            params['isParent'] = str(is_parent).lower()
        if member_no_list:
            params['memberNoList'] = member_no_list
        if contract_type_code:
            params['contractTypeCode'] = contract_type_code
        if contract_status_code:
            params['contractStatusCode'] = contract_status_code
        if region_code:
            params['regionCode'] = region_code
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
                
        return self.get('/cost/getContractSummaryList', params=params
    )

    def get_contract_usage_list(
        self,
        start_month: str,
        end_month: str,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        is_organization: Optional[bool] = None,
        is_parent: Optional[bool] = None,
        member_no_list: Optional[List[str]] = None,
        contract_no: Optional[str] = None,
        contract_type_code: Optional[str] = None,
        contract_status_code: Optional[str] = None,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        계약 사용량 목록을 조회합니다.
        
        Args:
            start_month: 조회 시작 월 (yyyyMM) 최대 3개월
            end_month: 조회 종료 월 (yyyyMM) 최대 3개월
            is_organization: 조직 고객 여부 (선택사항) (마스터만 사용가능 is_partner와 함께 사용 불가)
            is_parent: 파트너계정 조회 여부 (선택사항) (is_organization과 함께 사용 불가)
            member_no_list: 멤버 번호 리스트 (선택사항) (조직 고객 마스터만 사용가능)
            contract_no: 계약 번호 (선택사항)
            contract_type_code: 계약 구분 코드 (선택사항)
            contract_status_code: 계약 상태 코드 (선택사항) (ALL, NOML, NLEND)
            region_code: 지역 코드 (선택사항)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 계약별 사용량 내역 응답 데이터
        """
        params = {
            'startMonth': start_month,
            'endMonth': end_month
           
        }
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if is_organization and is_parent:
            raise ValueError("is_organization과 is_parent는 함께 사용할 수 없습니다.")
        if is_organization is not None:
            params['isOrganization'] = str(is_organization).lower()
        if is_parent is not None:
            params['isParent'] = str(is_parent).lower()
        if member_no_list:
            params['memberNoList'] = member_no_list
        if contract_no:
            params['contractNo'] = contract_no
        if contract_type_code:
            params['contractTypeCode'] = contract_type_code
        if contract_status_code:
            params['contractStatusCode'] = contract_status_code
        if region_code:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
                
        return self.get('/cost/getContractUsageList', params=params
    )

    def get_contract_usage_list_by_daily(
        self,
        use_start_date: str,
        use_end_date: str,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        is_organization: Optional[bool] = None,
        is_parent: Optional[bool] = None,
        member_no_list: Optional[List[str]] = None,
        contract_no: Optional[str] = None,
        contract_type_code: Optional[str] = None,
        product_item_kind_code: Optional[str] = None,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        설정 기간에 따라 일별 서비스 사용량을 조회합니다.
        
        Args:
            use_start_date: 조회 시작 일자 (yyyyMMdd) 최대 31일
            use_end_date: 조회 종료 일자 (yyyyMMdd) 최대 31일
            is_organization: 조직 고객 여부 (선택사항) (마스터만 사용가능 is_partner와 함께 사용 불가)
            is_parent: 파트너계정 조회 여부 (선택사항) (is_organization과 함께 사용 불가)
            member_no_list: 멤버 번호 리스트 (선택사항) (조직 고객 마스터만 사용가능)
            contract_no: 계약 번호 (선택사항)
            contract_type_code: 계약 구분 코드 (선택사항)
            product_item_kind_code: 상품 항목 종류 코드 (선택사항)
            region_code: 지역 코드 (선택사항)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 계약별 일별 사용량 내역 응답 데이터
        """
        params = {
            'use_start_date': use_start_date,
            'use_end_date': use_end_date
            
        }
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if is_organization and is_parent:
            raise ValueError("is_organization과 is_parent는 함께 사용할 수 없습니다.")  
        if is_organization is not None:
            params['isOrganization'] = str(is_organization).lower()
        if is_parent is not None:
            params['isParent'] = str(is_parent).lower()
        if member_no_list:
            params['memberNoList'] = member_no_list
        if contract_no:
            params['contractNo'] = contract_no
        if contract_type_code:
            params['contractTypeCode'] = contract_type_code
        if product_item_kind_code:
            params['productItemKindCode'] = product_item_kind_code     
        if region_code:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
                
        return self.get('/cost/getContractUsageListByDaily', params=params
    )

    def get_cost_relation_code_list(
        self,
        contract_type_code: Optional[str] = None,
        product_item_kind_code: Optional[str] = None,
        product_rating_type_code: Optional[str] = None,
        metering_type_code: Optional[str] = None,
        product_category_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        비용 연관 코드 목록을 조회합니다.
        비용 연관 코드는 
        사용량(getContractUsageList, 
        getContractUsageListByDaily) 또는 
        비용(getContractDemandCostList, 
        getProductDemandCostList) 조회 API에서 사용할 수 있습니다.
        
        Args:
            contract_type_code: 계약 유형 코드 (선택사항)
            product_item_kind_code: 상품 품목 종류 코드 (선택사항)
            product_rating_type_code: 상품 과금 유형 코드 (선택사항)
            metering_type_code: 미터링 구분 코드 (선택사항)
            product_category_code: 상품 카테고리 코드 (선택사항)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 비용 관련 코드 목록 응답 데이터
        """
        params = {}
        if contract_type_code:
            params['contractTypeCode'] = contract_type_code
        if product_item_kind_code:
            params['productItemKindCode'] = product_item_kind_code
        if product_rating_type_code:
            params['productRatingTypeCode'] = product_rating_type_code
        if metering_type_code:
            params['meteringTypeCode'] = metering_type_code
        if product_category_code:
            params['productCategoryCode'] = product_category_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/cost/getCostRelationCodeList', params=params)

    def get_demand_cost_list(
        self,
        start_month: str,
        end_month: str,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        is_organization: Optional[bool] = None,
        is_parent: Optional[bool] = None,
        member_no_list: Optional[List[str]] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        상품별 청구 내역을 조회합니다.
        
        Args:
            start_month: 조회 시작 월 (yyyyMM) 최대 3개월
            end_month: 조회 종료 월 (yyyyMM) 최대 3개월
            is_organization: 조직 고객 여부 (선택사항) (마스터만 사용가능 is_partner와 함께 사용 불가)
            is_parent: 파트너계정 조회 여부 (선택사항) (is_organization과 함께 사용 불가)
            member_no_list: 멤버 번호 리스트 (선택사항) (조직 고객 마스터만 사용가능)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 상품별 청구 내역 응답 데이터
        """
        params = {
            'startMonth': start_month,
            'endMonth': end_month
            
        }
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if is_organization and is_parent:
            raise ValueError("is_organization과 is_parent는 함께 사용할 수 없습니다.")
        if is_organization is not None:
            params['isOrganization'] = str(is_organization).lower()
        if is_parent is not None:
            params['isParent'] = str(is_parent).lower()
        if member_no_list:
            params['memberNoList'] = member_no_list
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/cost/getDemandCostList', params=params)
     
    def get_product_demand_cost_list(
        self,
        start_month: str,
        end_month: str,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        is_organization: Optional[bool] = None,
        is_parent: Optional[bool] = None,
        member_no_list: Optional[List[str]] = None,
        product_demand_type_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        설정 기간에 따라 서비스별 청구 비용 목록을 조회합니다.
        
        Args:
            start_month: 조회 시작 월 (yyyyMM) 최대 3개월
            end_month: 조회 종료 월 (yyyyMM) 최대 3개월
            is_organization: 조직 고객 여부 (선택사항) (마스터만 사용가능 is_partner와 함께 사용 불가)
            is_parent: 파트너계정 조회 여부 (선택사항) (is_organization과 함께 사용 불가)
            member_no_list: 멤버 번호 리스트 (선택사항) (조직 고객 마스터 또는 파트너 대표만 사용가능)
            product_demand_type_code: 서비스 청구유형 코드 (선택사항)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 서비스별 청구 비용 목록 응답 데이터

        """

        params = {
            'startMonth': start_month,
            'endMonth': end_month
            
        }

        if is_organization and is_parent:
            raise ValueError("is_organization과 is_parent는 함께 사용할 수 없습니다.")
        if is_organization is not None:
            params['isOrganization'] = str(is_organization).lower()
        if is_parent is not None:
            params['isParent'] = str(is_parent).lower()
        if member_no_list:
            params['memberNoList'] = member_no_list
        if product_demand_type_code:
            params['productDemandTypeCode'] = product_demand_type_code
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/cost/getProductDemandCostList', params=params)

        """
        ================================================================
         Region APIs
         ================================================================
        """
    def get_region_list(
        self,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        지역(Region) 목록을 조회합니다.
        
        Args:
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 지역 목록 응답 데이터
        """
        params = {}

        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
        return self.get('/region/getRegionList', params=params)
    
    """
    ===============================================================
    Discount APIs
    ===============================================================
    """

    def get_coin_history_list(
        self,
        discount_no_list: List[str],
        is_organization: Optional[bool] = None,
        is_parent: Optional[bool] = None,
        member_no_list: Optional[List[str]] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        계정에 부여된 코인의 현황과 사용 이력을 조회합니다.
        
        Args:
            discount_no_list: 조회할 코인번호 미입력시 전체 사용 이력
            is_organization: 조직 고객 여부 (선택사항) (마스터만 사용가능 is_partner와 함께 사용 불가)
            is_parent: 파트너계정 조회 여부 (선택사항) (is_organization과 함께 사용 불가)
            member_no_list: 멤버 번호 리스트 (선택사항) (조직 고객 마스터또는 파트너 대표만 사용가능)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 코인 사용 내역 응답 데이터
        """
        params = {}
        for idx, discount_no in enumerate(discount_no_list, start=1):
            params[f'discountNoList.{idx}'] = discount_no
        if is_organization and is_parent:
            raise ValueError("is_organization과 is_parent는 함께 사용할 수 없습니다.")  
        if is_organization is not None:
            params['isOrganization'] = str(is_organization).lower()
        if is_parent is not None:
            params['isParent'] = str(is_parent).lower()
        if member_no_list:
            for idx, member_no in enumerate(member_no_list, start=1):
                params[f'memberNoList.{idx}'] = member_no
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/discount/getCoinHistoryList', params=params)
    
    def get_credit_history_list(
        self,
        start_month: str,
        end_month: str,
        discount_no_list: List[str],
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        is_organization: Optional[bool] = None,
        is_parent: Optional[bool] = None,
        member_no_list: Optional[List[str]] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        크레딧 이력 목록을 조회합니다.
        
        Args:
            start_month: 조회 시작 월 (yyyyMM) 
            end_month: 조회 종료 월 (yyyyMM) 
            discount_no_list_N: 조회할 크레딧번호 미입력시 전체 사용 이력
            is_organization: 조직 고객 여부 (선택사항) (마스터만 사용가능 is_partner와 함께 사용 불가)
            is_parent: 파트너계정 조회 여부 (선택사항) (is_organization과 함께 사용 불가)
            member_no_list: 멤버 번호 리스트 (선택사항) (조직 고객 마스터또는 파트너 대표만 사용가능)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 크레딧 사용 내역 응답 데이터
        """
        params = {
            'startMonth': start_month,
            'endMonth': end_month
         
        }
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if discount_no_list:
            for idx, discount_no in enumerate(discount_no_list, start=1):
                params[f'discountNoList.{idx}'] = discount_no
        if is_organization and is_parent:
            raise ValueError("is_organization과 is_parent는 함께 사용할 수 없습니다.")  
        if is_organization is not None:
            params['isOrganization'] = str(is_organization).lower()
        if is_parent is not None:
            params['isParent'] = str(is_parent).lower()
        if member_no_list:
            params['memberNoList'] = member_no_list
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/discount/getCreditHistoryList', params=params)

    def get_discount_list(
        self,
        start_month: str,
        end_month: str,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        is_organization: Optional[bool] = None,
        is_parent: Optional[bool] = None,
        member_no_list: Optional[List[str]] = None,
        discount_type_code: Optional[str] = None,
        is_valid_discount: Optional[bool] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        할인 목록을 조회합니다.
        
        Args:
            start_month: 조회 시작 월 (yyyyMM) 최대 3개월
            end_month: 조회 종료 월 (yyyyMM) 최대 3개월
            is_organization: 조직 고객 여부 (선택사항) (마스터만 사용가능 is_partner와 함께 사용 불가)
            is_parent: 파트너계정 조회 여부 (선택사항) (is_organization과 함께 사용 불가)
            member_no_list: 멤버 번호 리스트 (선택사항) (조직 고객 마스터또는 파트너 대표만 사용가능)
            discount_type_code: 할인 유형 코드 (선택사항) (PRODUCT, CREDIT, COIN)
            is_valid_discount: 할인 유효 여부 (선택사항) (true, false)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 할인 목록 응답 데이터
        """
        params = {
            'startMonth': start_month,
            'endMonth': end_month
        }

        if is_organization and is_parent:
            raise ValueError("is_organization과 is_parent는 함께 사용할 수 없습니다.")
        if is_organization is not None:
            params['isOrganization'] = str(is_organization).lower()
        if is_parent is not None:
            params['isParent'] = str(is_parent).lower()
        if member_no_list:
            params['memberNoList'] = member_no_list
        if discount_type_code:
            params['discountTypeCode'] = discount_type_code
        if is_valid_discount is not None:
            params['isValidDiscount'] = str(is_valid_discount).lower()
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/discount/getDiscountList', params=params)

    def get_product_demand_cost_by_discount_list(
        self,
        start_month: str,
        end_month: str,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        product_demand_type_code_list: Optional[List[str]] = None,
        is_organization: Optional[bool] = None,
        is_parent: Optional[bool] = None,
        member_no_list: Optional[List[str]] = None,
        responseFormatType: Optional[str] = 'json'  
    ) -> Dict:
        """
        할인이 반영된 청구 내역을 조회합니다.

        Args:
            start_month: 조회 시작 월 (yyyyMM) 최대 3개월
            end_month: 조회 종료 월 (yyyyMM) 최대 3개월
            product_demand_type_code_list: 조회할 서비스 청구유형 (미입력시 전체 조회)
            is_organization: 조직 고객 여부 (선택사항) (마스터만 사용가능 is_partner와 함께 사용 불가)
            is_parent: 파트너계정 조회 여부 (선택사항) (is_organization과 함께 사용 불가)
            member_no_list: 멤버 번호 리스트 (선택사항) (조직 고객 마스터또는 파트너 대표만 사용가능)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 할인이 반영된 청구 내역 응답 데이터
        """
        params = {
            'startMonth': start_month,
            'endMonth': end_month
        }
        if is_organization and is_parent:
            raise ValueError("is_organization과 is_parent는 함께 사용할 수 없습니다.")
        if is_organization is not None:
            params['isOrganization'] = str(is_organization).lower()
        if is_parent is not None:
            params['isParent'] = str(is_parent).lower()
        if member_no_list:
            params['memberNoList'] = member_no_list
        if product_demand_type_code_list:
            for idx, product_demand_type_code in enumerate(product_demand_type_code_list, start=1):
                params[f'productDemandTypeCodeList.{idx}'] = product_demand_type_code
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/discount/getProductDemandCostByDiscountList', params=params)

    def get_product_discount_history_list(
        self,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        discount_no_list: Optional[List[str]] = None,
        is_organization: Optional[bool] = None,
        is_parent: Optional[bool] = None,
        member_no_list: Optional[List[str]] = None,
        start_month: Optional[str] = None,
        end_month: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict: 
        """
        계정에 부여된 서비스 요금 할인의 현황과 사용 이력을 조회합니다.
        
        Args:
            discount_no_list_N: 조회할 서비스 할인 번호 (미입력시 전체 조회)
            is_organization: 조직 고객 여부 (선택사항) (마스터만 사용가능 is_partner와 함께 사용 불가)
            is_parent: 파트너계정 조회 여부 (선택사항) (is_organization과 함께 사용 불가)
            member_no_list: 멤버 번호 리스트 (선택사항) (조직 고객 마스터또는 파트너 대표만 사용가능)
            start_month: 조회 시작 월 (yyyyMM) 
            end_month: 조회 종료 월 (yyyyMM)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 서비스 요금 할인 현황과 사용 이력 응답 데이터
        """
        params = {
            'responseFormatType': responseFormatType
        }
        if discount_no_list:
            for idx, discount_no in enumerate(discount_no_list, start=1):
                params[f'discountNoList.{idx}'] = discount_no   
        if is_organization and is_parent:
            raise ValueError("is_organization과 is_parent는 함께 사용할 수 없습니다.")
        if is_organization is not None:
            params['isOrganization'] = str(is_organization).lower()
        if is_parent is not None:
            params['isParent'] = str(is_parent).lower()
        if member_no_list:
            params['memberNoList'] = member_no_list
        if start_month:
            params['startMonth'] = start_month
        if end_month:
            params['endMonth'] = end_month
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
        return self.get('/discount/getProductDiscountHistoryList', params=params)