"""
NCP 플랫폼, 빌링 API 모듈

NCP 상품 가격정보, 사용비용, 할인정보 등을 조회하는 기능을 제공합니다.
"""

from typing import Dict, List, Optional
from ncp_api.base import BaseNCPAPI

class PlatformAPI(BaseNCPAPI):

    ENDPOINT_KEY = "platform"
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
            priceNoList.N	List<String>	Required	조회할 가격 번호 리스트 1~99
            promiseNoList.N	List<String>	Optional	조회할 약정 번호 리스트
            payCurrencyCode	String	Optional	결제 통화 코드            KRW | USD | JPY
            responseFormatType	String	Optional	응답 결과의 형식             xml (기본값) | json
        
        Returns:
            Dict: 
                totalRows	Integer	Required	조회된 목록의 총 개수 페이징 처리 요청의 경우 전체 개수
                priceList	List<Price>	Required	List<Price> 데이터 타입
                    priceNo	String	Required	가격 번호
                        priceType	CommonCode	Required	요금제 구분 코드 FREE | FXSUM | MTRAT  FREE: 무료 FXSUM: 월정액제 MTRAT: 종량제
                        region	Region	Required	리전
                        chargingUnitType	CommonCode	Required	과금 측정 기준  QUERY | TIME | TMCU | USER   QUERY: 쿼리 TIME: 시간 TMCU (Time and vCPU Count): 시간 및 vCPU 개수 USER: 보장 회원 수
                        ratingUnitType	CommonCode	Required	과금 단위 구분 코드 CNTRY | POINT | SECT | PKG
                        CNTRY: 국가 요금제(국가별 다른 요금제 적용)
                        POINT: 점 단위(사용한 만큼 적용)
                        SECT: 구간 요금제(구간별 요금제 별도 적용)
                        PKG: 패키지 요금제(패키지에 기술된 상품 과금 유형 코드별 무료 사용량 적용)
                        chargingUnitBasicValue	String	Required	과금 단위 구분 값 과금 측정 기준 코드 값에 해당하는 수
                        productRatingType	CommonCode	Required	상품 과금 유형
                        unit	CommonCode	Required	단위
                        price	Double	Required	가격
                        conditionType	CommonCode	Required	조건 단위
                        conditionPrice	Double	Required	조건 가격
                        priceDescription	String	Required	요금 설명
                        freeUnit	CommonCode	Required	무료 단위
                        freeValue	Long	Required	무료 값
                        meteringUnit	CommonCode	Required	미터링 단위
                        startDate	Date	Required	판매 시작 일시
                        priceAttribute	CommonCode	Required	요금제 속성
                        priceVersionName	String	Required	요금제 버전명
                        payCurrency	CommonCode	Required	결제 통화
                        periodUnitList	List<PeriodUnit>	Required	구간 단위 목록
                        countryUnitList	List<CountryUnit>	Required	국가 단위 목록
                        packageUnitList	List<PackageUnit>	Required	패키지 단위 목록
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
        
        return self.client.get('/product/getPriceList', params=params)
    
    def get_product_category_list(
        self,
        product_category_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        서비스 카테고리 목록을 조회합니다.
        
        Args:
            product_category_code: 상품 카테고리 코드 (선택사항)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 상품 카테고리 응답 데이터
                totalRows	Integer	Required	조회된 목록의 총 개수 페이징 처리 요청의 경우 전체 개수
                productCategoryList	List<CommonCode>	Required	List<CommonCode> 데이터 타입
                    code	String	Required	5 자리 이내의 코드 INIT | CREAT | RUN | NSTOP
                    codeName	String	Required	코드에 해당하는 코드 이름 INIT 상태 | 생성 | 운영 | 정상 정지
        """
        params = {}

        if product_category_code is not None:
            params['productCategoryCode'] = product_category_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.client.get('/product/getProductCategoryList', params=params)   
    
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
        서비스 목록을 조회합니다.
        
        Args:

            pageNo	Integer	Optional	페이지 번호
            pageSize	Integer	Optional	페이지 크기             1,000 이하(기본값: 1,000)
            regionCode	String	Required	리전 코드
            getRegionList 액션을 통해 확인
            productItemKindCode	String	Optional	상품 품목 종류 코드
            productCategoryCode	String	Optional	상품 카테고리 코드
            getProductCategoryList 액션을 통해 확인
            productCode	String	Optional	상품 코드
            productName	String	Optional	상품명
            responseFormatType	String	Optional	응답 결과의 형식            xml (기본값) | json
       
        Returns:
            Dict: 상품 목록 응답 데이터
                totalRows	Integer	Required	조회된 목록의 총 개수 페이징 처리 요청의 경우 전체 개수
                productList	List<Product>	Required	List<Product> 데이터 타입
                    productItemKind	CommonCode	Required	상품 품목 종류
                    productItemKindDetail	CommonCode	Required	상품 품목 종류 상세
                    productCode	String	Required	상품 코드
                    productName	String	Required	상품명
                    productDescription	String	Required	상품 설명
                    softwareType	CommonCode	Required	소프트웨어 유형 코드
                    productCategory	CommonCode	Required	상품 카테고리
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

        return self.client.get('/product/getProductList', params=params)
    
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
            pageNo	Integer	Optional	페이지 번호
            pageSize	Integer	Optional	페이지 크기             1,000 이하(기본값: 1,000)
            regionCode	String	Required	리전 코드
            getRegionList 액션을 통해 확인
            productItemKindCode	String	Optional	상품 품목 종류 코드
            productCategoryCode	String	Optional	상품 카테고리 코드
            getProductCategoryList 액션을 통해 확인
            productCode	String	Optional	상품 코드
            productName	String	Optional	상품명
            payCurrencyCode	String	Optional	결제 통화 코드             KRW | USD | JPY
            responseFormatType	String	Optional	응답 결과의 형식             xml (기본값) | json
        
        Returns:
            Dict: 상품 가격 목록 응답 데이터
                totalRows	Integer	Required	조회된 목록의 총 개수   페이징 처리 요청의 경우 전체 개수
                productPriceList	List<ProductPrice>	Required	List<ProductPrice> 데이터 타입
                    productItemKind	CommonCode	Required	상품 품목 종류
                    productItemKindDetail	CommonCode	Required	상품 품목 종류 상세
                    productCode	String	Required	상품 코드
                    productName	String	Required	상품명
                    productDescription	String	Required	상품 설명
                    softwareType	CommonCode	Required	소프트웨어 유형
                    productCategory	CommonCode	Required	상품 카테고리
                    productType	CommonCode	Required	상품 유형
                    productTypeDetail	CommonCode	Required	상품 유형 상세
                    gpuCount	Integer	Required	GPU 수  서버 상품 조회 시 리턴됨
                    cpuCount	Integer	Required	CPU 수  서버 상품 조회 시 리턴됨
                    memorySize	Long	Required	메모리 사이즈(Byte) 서버 상품 조회 시 리턴됨
                    baseBlockStorageSize	Long	Required	기본 블록 스토리지 사이즈(Byte)  서버 상품 조회 시 리턴됨
                    dbKind	CommonCode	Required	데이터베이스 유형 코드  Cloud DB에 관련된 서버 상품 조회 시 리턴됨
                    osInfomation	String	Required	OS 정보
                    platformType	CommonCode	Required	플랫폼 구분
                    osType	CommonCode	Required	OS 구분
                    platformCategoryCode	String	Required	플랫폼 카테고리 코드 <예시> APP, DBMS, OS
                    diskType	CommonCode	Required	디스크 유형
                    diskDetailType	CommonCode	Required	디스크 상세 유형
                    generationCode	String	Required	상품 세대 코드    G1 | G2
                    priceList	List<Price>	Required	요금제 목록  해당 상품이 사용하는 요금제 정보 목록
                        priceNo	String	Required	가격 번호
                        priceType	CommonCode	Required	요금제 구분 코드      FREE | FXSUM | MTRAT         FREE: 무료 FXSUM: 월정액제 MTRAT: 종량제
                        region	Region	Required	리전
                        chargingUnitType	CommonCode	Required	과금 측정 기준 QUERY | TIME | TMCU | USER  QUERY: 쿼리 TIME: 시간 TMCU (Time and vCPU Count): 시간 및 vCPU 개수 USER: 보장 회원 수
                        ratingUnitType	CommonCode	Required	과금 단위 구분 코드 DETAIL | POINT | SECT | PKG DETAIL: 상세 요금제(상세 유형별 다른 요금제 적용) POINT: 점 단위(사용한 만큼 적용) SECT: 구간 요금제(구간별 요금제 별도 적용) PKG: 패키지 요금제(패키지에 기술된 상품 과금 유형 코드별 무료 사용량 적용)
                        detailFeeCategory	CommonCode	Required	상세 요금 카테고리 CNTRY | RGN | ITEM_DETAIL | NULL CNTRY: 국가 요금제(국가별 다른 요금제 적용) RGN: 리전 요금제(리전별 다른 요금제 적용) ITEM_DETAIL: 일반 요금제 PKG: 구분 없음
                        ratingUnitTypeDetail	CommonCode	Required	상세 요금 카테고리  POINT | SECT POINT: 점 단위(사용한 만큼 적용) SECT: 구간 요금제(구간별 요금제 별도 적용)
                        chargingUnitBasicValue	String	Required	과금 단위 구분 값                        과금 측정 기준 코드 값에 해당하는 수
                        productRatingType	CommonCode	Required	상품 과금 유형
                        unit	CommonCode	Required	단위
                        price	Double	Required	가격
                        conditionType	CommonCode	Required	조건 단위
                        conditionPrice	Double	Required	조건 가격
                        priceDescription	String	Required	요금 설명
                        freeUnit	CommonCode	Required	무료 단위
                        freeValue	Long	Required	무료 값
                        meteringUnit	CommonCode	Required	미터링 단위
                        startDate	Date	Required	판매 시작 일시
                        priceAttribute	CommonCode	Required	요금제 속성
                        priceVersionName	String	Required	요금제 버전명
                        payCurrency	CommonCode	Required	결제 통화
                        periodUnitList	List<PeriodUnit>	Required	구간 단위 목록
                        detailUnitList	List<DetailUnit>	Required	상세 단위 목록
                        packageUnitList	List<PackageUnit>	Required	패키지 단위 목록

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
        

        return self.client.get('/product/getProductPriceList', params=params)
    
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
        설정 기간에 따라 월 계약 청구 비용 목록을 조회합니다.
        
        Args:
            pageNo	Integer	Optional	페이지 번호
            pageSize	Integer	Optional	페이지 크기 1,000 이하(기본값: 1,000)
            isOrganization	Boolean	Optional	Organization 서비스 계정 통합 조회 여부 마스터만 사용 가능            isOrganization, isPartner 모두 true이면 에러 응답
            isPartner	Boolean	Optional	파트너 계정 조회 여부 파트너 대표만 사용 가능            isOrganization, isPartner 모두 true이면 에러 응답
            memberNoList	List<String>	Optional	회원 번호 목록 마스터 또는 파트너 대표만 사용 가능
            contractNo	String	Optional	계약 번호
            startMonth	String	Required	조회 시작 월(yyyyMM) 최대 3개월 조회 가능 <예시> 202401
            endMonth	String	Required	조회 마지막 월(yyyyMM) 최대 3개월 조회 가능 <예시> 202403
            demandTypeCode	String	Optional	청구 유형 코드
            demandTypeDetailCode	String	Optional	청구 유형 상세 코드 
            regionCode	String	Optional	리전 코드  getRegionList 액션을 통해 확인
            responseFormatType	String	Optional	응답 결과의 형식 xml (기본값) | json
        
        Returns:
            Dict: 계약별 청구 내역 응답 데이터
                totalRows	Integer	Required	조회된 목록의 총 개수 페이징 처리 요청의 경우 전체 개수
                ContractDemandCostList	List<ContractDemandCost>	Required	List<ContractDemandCost> 데이터 타입
                    memberNo	String	Required	회원 번호
                    regionCode	String	Required	리전 코드
                    demandType	CommonCode	Required	청구 유형 코드
                    demandTypeDetail	CommonCode	Required	청구 유형 상세 코드
                    contract	Contract	Required	계약 정보
                    demandMonth	String	Required	청구 월
                    unitUsageQuantity	Double	Required	단위 사용량
                    packageUnitUsageQuantity	Double	Required	패키지 단위 사용량
                    totalUnitUsageQuantity	Double	Required	총 단위 사용량
                    usageUnit	CommonCode	Required	사용량 단위
                    productPrice	Double	Required	상품 가격
                    useAmount	Double	Required	사용 금액
                    promotionDiscountAmount	Double	Required	프로모션 할인 금액
                    etcDiscountAmount	Double	Required	기타 할인 금액
                    promiseDiscountAmount	Double	Required	약정 할인 금액
                    demandAmount	Double	Required	청구 금액
                    writeDate	Date	Required	작성 일시(YYYY-MM-DDThh:mm:ssZ)
                    memberPriceDiscountAmount	Double	Required	회원 요금제 할인 금액
                    memberPromiseDiscountAddAmount	Double	Required	회원 약정 요금제 할인 금액
                    payCurrency	CommonCode	Required	결제 통화
                    thisMonthAppliedExchangeRate	Double	Required	이번 달 적용 환율
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
                
        return self.client.get('/cost/getContractDemandCostList', params=params)
    
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
            pageNo	Integer	Optional	페이지 번호
            pageSize	Integer	Optional	페이지 크기 1,000 이하(기본값: 1,000)
            isOrganization	Boolean	Optional	Organization 하위 계정의 통합 사용량 조회 여부 마스터만 사용 가능 isOrganization, isPartner 모두 true이면 에러 응답
            isPartner	Boolean	Optional	파트너 계정 조회 여부 파트너 대표만 사용 가능 isOrganization, isPartner 모두 true이면 에러 응답
            memberNoList	List<String>	Optional	회원 번호 목록 마스터 또는 파트너 대표만 사용 가능
            contractMonth	String	Required	조회할 계약 연월(yyyyMM) <예시> 202404
            contractTypeCode	String	Optional	계약 유형 코드
            contractStatusCode	String	Optional	계약 상태 코드 ALL (기본값) | NOML | NLEND ALL: 모두 NOML: 정상 NLEND: 종료
            regionCode	String	Optional	리전 코드 regionCode는 getRegionList 액션을 통해서 획득 가능
            responseFormatType	String	Optional	응답 결과의 형식 xml (기본값) | json
                    
        Returns:
            Dict: 계약별 요약 내역 응답 데이터
                totalRows	Integer	Required	조회된 목록의 총 개수 페이징 처리 요청의 경우 전체 개수
                contractSummaryList	List<ContractSummary>	Required	List<ContractSummary> 데이터 타입
                    memberNo	String	Required	회원 번호
                    regionCode	String	Required	리전 코드
                    contractType	CommonCode	Required	계약 유형 코드
                    contractCount	Integer	Required	계약 수
                    contractStatus	CommonCode	Required	계약 상태

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
                
        return self.client.get('/cost/getContractSummaryList', params=params
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
            pageNo	Integer	Optional	페이지 번호
            pageSize	Integer	Optional	페이지 크기 1,000 이하(기본값: 1,000)
            isOrganization	Boolean	Optional	Organization 서비스 계정 통합 조회 여부 마스터만 사용 가능 isOrganization, isPartner 모두 true이면 에러 응답
            isPartner	Boolean	Optional	파트너 계정 조회 여부 파트너 대표만 사용 가능 isOrganization, isPartner 모두 true이면 에러 응답
            memberNoList	List<String>	Optional	회원 번호 목록 마스터 또는 파트너 대표만 사용 가능
            contractNo	String	Optional	계약 번호
            startMonth	String	Required	조회 시작 월(yyyyMM) 최대 3개월 조회 가능 <예시> 202401
            endMonth	String	Required	조회 마지막 월(yyyyMM) 최대 3개월 조회 가능 <예시> 202403
            contractTypeCode	String	Optional	계약 유형 코드
            contractStatusCode	String	Optional	계약 상태 코드 NOML | NLEND NOML: 정상 NLEND: 종료
            regionCode	String	Optional	리전 코드
            getRegionList 액션을 통해서 획득 가능
            responseFormatType	String	Optional	응답 결과의 형식 xml (기본값) | json
                    
        Returns:
            Dict: 계약별 사용량 내역 응답 데이터
                totalRows	Integer	Required	조회된 목록의 총 개수 페이징 처리 요청의 경우 전체 개수
                contractList	List<Contract>	Required	List<Contract> 데이터 타입
                    memberNo	String	Required	회원 번호
                    contractNo	String	Required	계약 번호
                    conjunctionContractNo	String	Required	연관 계약 번호
                    contractType	CommonCode	Required	계약 구분
                    contractStatus	CommonCode	Required	계약 상태
                    contractStartDate	Date	Required	계약 시작 일시
                    contractEndDate	Date	Required	계약 종료 일시
                    instanceName	String	Required	인스턴스 이름
                    regionCode	String	Required	리전 코드
                    platformType	CommonCode	Required	플랫폼 구분
                    contractProductList	List<ContractProduct>	Required	계약 상품 목록
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
                
        return self.client.get('/cost/getContractUsageList', params=params
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
            pageNo	Integer	Optional	페이지 번호
            pageSize	Integer	Optional	페이지 크기 1,000 이하(기본값: 1,000)
            isOrganization	Boolean	Optional	Organization 서비스 계정 통합 조회 여부 마스터만 사용 가능 isOrganization, isPartner 모두 true이면 에러 응답
            isPartner	Boolean	Optional	파트너 계정 조회 여부 파트너 대표만 사용 가능 isOrganization, isPartner 모두 true이면 에러 응답
            memberNoList	List<String>	Optional	회원 번호 목록 마스터 또는 파트너 대표만 사용 가능
            contractNo	String	Optional	계약 번호
            useStartDay	String	Required	조회 시작 일(yyyyMMdd) 최대 3개월 조회 가능 <예시> 20240101
            useEndDay	String	Required	조회 마지막 일(yyyyMMdd) 최대 3개월 조회 가능 <예시> 20240331
            contractTypeCode	String	Optional	계약 유형 코드
            productItemKindCode	String	Optional	서비스 품목 종류 코드
            regionCode	String	Optional	리전 코드 getRegionList 액션을 통해 확인
            responseFormatType	String	Optional	응답 결과의 형식 xml (기본값) | json
        
        Returns:
            Dict: 계약별 일별 사용량 내역 응답 데이터
                totalRows	Integer	Required	조회된 목록의 총 개수 페이징 처리 요청의 경우 전체 개수
                contractUsageListByDaily	List<ContractUsageByDaily>	Required	List<ContractUsageByDaily> 데이터 타입
                    account	Account	Required	계정
                    useDate	UseDate	Required	사용 일자
                    contract	Contract	Required	계약
                    contractProduct	ContractProduct	Required	계약 상품
                    usage	Usage	Required	사용량
        """
        params = {
            'useStartDay': use_start_date,
            'useEndDay': use_end_date
            
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
                
        return self.client.get('/cost/getContractUsageListByDaily', params=params
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
            contractTypeCode	String	Optional	계약 유형 코드
            productItemKindCode	String	Optional	상품 품목 종류 코드
            productRatingTypeCode	String	Optional	상품 과금 유형 코드
            meteringTypeCode	String	Optional	미터링 구분 코드
            productCategoryCode	String	Optional	상품 카테고리 코드
            getProductCategoryList 액션을 통해 확인
            responseFormatType	String	Optional	응답 결과의 형식 xml (기본값) | json

        
        Returns:
            Dict: 비용 관련 코드 목록 응답 데이터
            totalRows	Integer	Required	조회된 목록의 총 개수 페이징 처리 요청의 경우 전체 개수
            costRelationCodeList	List<CostRelationCode>	Required	List<CostRelationCode> 데이터 타입
                contractType	CommonCode	Required	계약 구분
                productItemKind	CommonCode	Required	상품 품목 종류
                productRatingType	CommonCode	Required	상품 과금 유형
                meteringType	CommonCode	Required	미터링 구분
                demandType	CommonCode	Required	청구 유형
                demandTypeDetail	CommonCode	Required	청구 유형 상세
                productDemandType	ProductDemandType	Required	상품 청구 유형
                productCategory	CommonCode	Required	상품 카테고리
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

        return self.client.get('/cost/getCostRelationCodeList', params=params)

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
        설정 기간에 따라 월 청구 비용에 대한 목록을 조회합니다.
        
        Args:
            pageNo	Integer	Optional	페이지 번호
            pageSize	Integer	Optional	페이지 크기             1,000 이하(기본값: 1,000)
            isOrganization	Boolean	Optional	Organization 서비스 계정 통합 조회 여부 마스터만 사용 가능 isOrganization, isPartner 모두 true이면 에러 응답
            isPartner	Boolean	Optional	파트너 계정 조회 여부             파트너 대표만 사용 가능             isOrganization, isPartner 모두 true이면 에러 응답
            memberNoList	List<String>	Optional	회원 번호 목록             마스터 또는 파트너 대표만 사용 가능
            startMonth	String	Required	조회 시작 월(yyyyMM)            최대 3개월 조회 가능            <예시> 202401
            endMonth	String	Required	조회 마지막 월(yyyyMM)            최대 3개월 조회 가능            <예시> 202403
            responseFormatType	String	Optional	응답 결과의 형식            xml (기본값) | json
        
        Returns:
            Dict: 상품별 청구 내역 응답 데이터
                totalRows	Integer	Required	조회된 목록의 총 개수 페이징 처리 요청의 경우 전체 개수
                demandCostList	List<DemandCost>	Required	List<DemandCost> 데이터 타입
                    memberNo	String	Required	회원 번호
                    demandMonth	String	Required	청구 월
                    demandNo	String	Required	청구 번호
                    integrationDemandNo	String	Required	통합 청구 번호
                    demandAttribute	CommonCode	Required	청구 속성
                    useAmount	Double	Required	사용 금액
                    promiseDiscountAmount	Double	Required	약정 할인 금액
                    promotionDiscountAmount	Double	Required	프로모션 할인 금액
                    etcDiscountAmount	Double	Required	기타 할인 금액
                    customerDiscountAmount	Double	Required	고객 할인 금액
                    productDiscountAmount	Double	Required	상품 할인 금액
                    creditDiscountAmount	Double	Required	크레딧 할인 금액
                    rounddownDiscountAmount	Double	Required	절사 할인 금액
                    currencyDiscountAmount	Double	Required	통화 할인 금액
                    coinUseAmount	Double	Required	코인 사용 금액
                    defaultAmount	Double	Required	위약 금액
                    thisMonthDemandAmount	Double	Required	이번 달 청구 금액 및 위약금 합산 금액 (이번 달 청구, VAT 합산 금액 및 미납 총액 합산)
                    thisMonthVatRatio	Float	Required	이번 달 적용 VAT 비율
                    thisMonthVatAmount	Double	Required	이번 달 VAT 금액
                    thisMonthAmountIncludingVat	Double	Required	이번 달 청구, VAT 합산 금액
                    totalDemandAmount	Double	Required	총 청구 합산
                    isPaidUp	Boolean	Required	지불 완료 여부                     true | false
                    paidUpDate	Date	Required	지불 일시
                    overdueOccurDate	Date	Required	미납 발생 일시
                    overduePlusAmount	Double	Required	미납 가산금 금액
                    overdueRatio	Float	Required	미납 가산금 비율
                    thisMonthOverdueAmount	Double	Required	이번 달 미납 금액
                    beforeMonthDemandNo	String	Required	지난 달 청구 번호
                    totalOverdueAmount	Double	Required	미납 총액 (전월 미납 금액 및 미납 가산금 합산)
                    writeDate	Date	Required	작성 일시(YYYY-MM-DDThh:mm:ssZ)
                    memberPriceDiscountAmount	Double	Required	회원 요금제 할인 금액
                    memberPromiseDiscountAddAmount	Double	Required	회원 약정 요금제 할인 금액
                    payCurrency	CommonCode	Required	결제 통화
                    thisMonthAppliedExchangeRate	Double	Required	이번 달 적용 환율
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

        return self.client.get('/cost/getDemandCostList', params=params)
     
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
            pageNo	Integer	Optional	페이지 번호
            pageSize	Integer	Optional	페이지 크기            1,000 이하(기본값: 1,000)
            isOrganization	Boolean	Optional	Organization 서비스 계정 통합 조회 여부            마스터만 사용 가능            isOrganization, isPartner 모두 true이면 에러 응답
            isPartner	Boolean	Optional	파트너 계정 조회 여부            파트너 대표만 사용 가능            isOrganization, isPartner 모두 true이면 에러 응답
            memberNoList	List<String>	Optional	회원 번호 목록            마스터 또는 파트너 대표만 사용 가능
            startMonth	String	Required	조회 시작 월(yyyyMM)            최대 3개월 조회 가능            <예시> 202401
            endMonth	String	Required	조회 마지막 월(yyyyMM)            최대 3개월 조회 가능            <예시> 202403
            productDemandTypeCode	String	Optional	서비스 청구 유형 코드
            responseFormatType	String	Optional	응답 결과의 형식            xml (기본값) | json
        
        Returns:
            Dict: 서비스별 청구 비용 목록 응답 데이터
                totalRows	Integer	Required	조회된 목록의 총 개수페이징 처리 요청의 경우 전체 개수
                productDemandCostList	List<ProductDemandCost>	Required	List<ProductDemandCost> 데이터 타입
                    memberNo	String	Required	회원 번호
                    demandMonth	String	Required	청구 월
                    productDemandType	ProductDemandType	Required	상품 청구 유형
                    promiseDiscountAmount	Long	Required	약정 할인 금액
                    promotionDiscountAmount	Long	Required	프로모션 할인 금액
                    etcDiscountAmount	Long	Required	기타 할인 금액
                    productDiscountAmount	Long	Required	상품 할인 금액
                    creditDiscountAmount	Long	Required	크레딧 할인 금액
                    defaultAmount	Long	Required	위약 금액
                    useAmount	Long	Required	사용 금액
                    demandAmount	Long	Required	청구 금액
                    writeDate	Date	Required	작성 일시(YYYY-MM-DDThh:mm:ssZ)
                    memberPriceDiscountAmount	Long	Required	회원 요금제 할인 금액
                    memberPromiseDiscountAddAmount	Long	Required	회원 약정 요금제 할인 금액
                    payCurrency	CommonCode	Required	결제 통화
                    thisMonthAppliedExchangeRate	Double	Required	이번 달 적용 환율

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

        return self.client.get('/cost/getProductDemandCostList', params=params)

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
        사용 가능한 리전 목록을 조회합니다.
        
        Args:
            regionCode	String	Optional	조회할 리전 코드 getRegionList 액션을 통해 확인
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 지역 목록 응답 데이터
            totalRows	Integer	Required	조회된 목록의 총 개수 페이징 처리 요청의 경우 전체 개수
            regionList	List<Region>	Required	List<Region> 데이터 타입
                regionNo	Integer	Required	리전 번호
                regionCode	String	Required	리전 코드
                regionName	String	Required	리전 이름
        """
        params = {}

        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
        return self.client.get('/region/getRegionList', params=params)
    
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
            pageNo	Integer	Optional	페이지 번호
            pageSize	Integer	Optional	페이지 크기 1,000 이하(기본값: 1,000)
            discountNoList.N	List<String>	Optional	조회할 코인 번호 미 입력 시 전체 코인의 사용 이력 응답 코인 번호는 getDiscountList 액션을 통해 확인
            isOrganization	Boolean	Optional	Organization 서비스 계정 통합 조회 여부 마스터만 사용 가능
            isOrganization, isPartner 모두 true이면 에러 응답
            isPartner	Boolean	Optional	파트너 계정 조회 여부 파트너 대표만 사용 가능 isOrganization, isPartner 모두 true이면 에러 응답
            memberNoList.N	List<String>	Optional	회원 번호 목록 마스터 또는 파트너 대표만 사용 가능
            responseFormatType	String	Optional	응답 결과의 포맷 유형 xml (기본값) | json
        Returns:
            Dict: 코인 사용 내역 응답 데이터
            totalRows	Integer	Required	조회된 목록의 총 개수 페이징 처리 요청의 경우 전체 개수
            coinHistoryList	List<CoinHistory>	Required	List<CoinHistory> 데이터 타입
                memberNo	String	Required	회원 번호
                coin	Coin	Required	코인
                coinUseHistory	List<CoinUseHistory>	Required	List<CoinUseHistory> 데이터 타입
                    memberNo	String	Required	회원번호 코인 보유한 계정의 회원번호
                    sharedMemberNo	String	Required	회원번호 코인 사용 계정의 회원번호
                    useMonth	String	Required	사용 월
                    unusedCoin	Double	Required	미사용 코인
                    usedCoin	Double	Required	사용 코인
                    remainingCoin	Double	Required	남은 코인

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

        return self.client.get('/discount/getCoinHistoryList', params=params)
    
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
            pageNo	Integer	Optional	페이지 번호
            pageSize	Integer	Optional	페이지 크기 1,000 이하(기본값: 1,000)
            discountNoList.N	List<String>	Optional	조회할 크레딧 번호 미 입력 시 전체 크레딧 사용 이력 응답 크레딧 번호는 getDiscountList 액션을 통해 확인
            isOrganization	Boolean	Optional	Organization 서비스 계정 통합 조회 여부 마스터만 사용 가능 isOrganization, isPartner 모두 true이면 에러 응답
            isPartner	Boolean	Optional	파트너 계정 조회 여부 파트너 대표만 사용 가능 isOrganization, isPartner 모두 true이면 에러 응답
            memberNoList	List<String>	Optional	회원 번호 목록 마스터 또는 파트너 대표만 사용 가능
            startMonth	String	Optional	조회 시작 월(yyyyMM) <예시> 202401 
            endMonth	String	Optional	조회 마지막 월(yyyyMM) <예시> 202403
            responseFormatType	String	Optional	응답 결과의 형식 xml (기본값) | json
        
        Returns:
            Dict: 크레딧 사용 내역 응답 데이터
            totalRows	Integer	Required	조회된 목록의 총 개수 페이징 처리 요청의 경우 전체 개수
            creditHistoryList	List<CreditHistory>	Required	List<CreditHistory> 데이터 타입
                memberNo	String	Required	회원 번호
                credit	Credit	Required	크레딧
                creditUseHistory	List<CreditUseHistory>	Required	List<CreditUseHistory> 데이터 타입
                    useMonth	String	Required	사용 월
                    productDemandType	ProductDemandType	Required	상품 청구 유형
                    unusedCredit	Double	Required	미사용 크레딧
                    usedCredit	Double	Required	사용 크레딧
                    remainingCredit	Double	Required	남은 크레딧
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

        return self.client.get('/discount/getCreditHistoryList', params=params)

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
        계정이 보유하고 있는 할인 목록을 조회합니다.
        
        Args:
            pageNo	Integer	Optional	페이지 번호
            pageSize	Integer	Optional	페이지 크기 1,000 이하(기본값: 1,000)
            isOrganization	Boolean	Optional	Organization 서비스 계정 통합 조회 여부 마스터만 사용 가능 isOrganization, isPartner 모두 true이면 에러 응답
            isPartner	Boolean	Optional	파트너 계정 조회 여부 파트너 대표만 사용 가능 isOrganization, isPartner 모두 true이면 에러 응답
            memberNoList	List<String>	Optional	회원 번호 목록 마스터 또는 파트너 대표만 사용 가능
            discountTypeCode	String	Optional	할인 유형 PRODUCT | CREDIT | COIN PRODUCT: 서비스 요금 할인 CREDIT: 크레딧 COIN: 코인
            startMonth	String	Optional	조회 시작 월(yyyyMM) 최대 3개월 조회 가능 <예시> 202401
            endMonth	String	Optional	조회 마지막 월(yyyyMM) 최대 3개월 조회 가능 <예시> 202403
            isValidDiscount	Boolean	Optional	유효한 할인만 조회 여부 true | false true: 유효한 할인만 조회 false: 모든 할인 조회
            responseFormatType	String	Optional	응답 결과의 형식 xml (기본값) | json
        
        Returns:
            Dict: 할인 목록 응답 데이터
            totalRows	Integer	Required	조회된 목록의 총 개수 페이징 처리 요청의 경우 전체 개수 
            demandCostList	List<Discount>	Required	List<Discount> 데이터 타입
                memberNo	String	Required	회원 번호
                discountNo	String	Required	할인 번호
                discountType	CommonCode	Required	할인 유형
                discountName	String	Required	할인명
                discountProcessMethod	CommonCode	Required	할인 방식
                discountValue	Double	Required	할인 값
                validityStartMonth	String	Required	적용 시작 월
                validityEndMonth	String	Required	적용 종료 월
                payCurrency	CommonCode	Required	결제 통화
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

        return self.client.get('/discount/getDiscountList', params=params)

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
            startMonth	String	Required	조회 시작 월(yyyyMM) 최대 6개월 조회 가능 <예시> 202401
            endMonth	String	Required	조회 마지막 월(yyyyMM) 최대 6개월 조회 가능 <예시> 202406
            pageNo	Integer	Optional	페이지 번호
            pageSize	Integer	Optional	페이지 크기 1,000 이하(기본값: 1,000)
            productDemandTypeCodeList.N	List	Optional	조회할 서비스 청구 유형 코드 미 입력 시 전체 청구 목록 응답
            isOrganization	Boolean	Optional	Organization 서비스 계정 통합 조회 여부 마스터만 사용 가능 isOrganization, isPartner 모두 true이면 에러 응답
            isPartner	Boolean	Optional	파트너 계정 조회 여부 파트너 대표만 사용 가능 isOrganization, isPartner 모두 true이면 에러 응답
            memberNoList	List<String>	Optional	회원 번호 목록 마스터 또는 파트너 대표만 사용 가능
            responseFormatType	String	Optional	응답 결과의 형식 xml (기본값) | json
        
        Returns:
            Dict: 할인이 반영된 청구 내역 응답 데이터
            totalRows	Integer	Required	조회된 목록의 총 개수 페이징 처리 요청의 경우 전체 개수
            productDemandCostByDiscountList	List<ProductDemandCostByDiscount>	Required	List<ProductDemandCostByDiscount> 데이터 타입
                memberNo	String	Required	회원 번호
                demandMonth	String	Required	청구 월
                productDemandType	ProductDemandType	Required	상품 청구 유형
                promiseDiscountAmount	Double	Required	약정 할인 금액
                promotionDiscountAmount	Double	Required	프로모션 할인 금액
                etcDiscountAmount	Double	Required	기타 할인 금액
                productDiscountAmount	Double	Required	상품 할인 금액
                creditDiscountAmount	Double	Required	크레딧 할인 금액
                defaultAmount	Double	Required	위약 금액
                useAmount	Double	Required	사용 금액
                demandAmount	Double	Required	청구 금액
                writeDate	Date	Required	작성 일시(YYYY-MM-DDThh:mm:ssZ)
                memberPriceDiscountAmount	Double	Required	회원 요금제 할인 금액
                memberPromiseDiscountAddAmount	Double	Required	회원 약정 요금제 할인 금액
                discountAppliedCount	Integer	Required	해당 상품에 당월 적용된 상품 할인 수
                appliedCreditHistoryList	List<AppliedCreditHistory>	Required	적용된 크레딧 이력 목록
                    discountTargetAmount	Double	Required	할인 대상 금액
                    discountAppliedamount	Double	Required	할인 적용 금액
                    discountNo	String	Required	할인 번호
                    creditName	String	Required	크레딧 이름
                    receivedCredit	Double	Required	최초 부여된 크레딧 금액
                    remainingCredit	Double	Required	남은 크레딧
                    validityStartMonth	String	Required	유효 시작 월
                    validityEndMonth	String	Required	유효 종료 월
                    creditType	CommonCode	Required	크레딧 타입
                    eligibleProductDemandTypeList	List<ProductDemandType>	Required	할인 가능한 상품 청구 유형 목록
                appliedProductDiscountHistoryList	List<AppliedProductDiscountHistory>	Required	적용된 상품 할인 이력 목록
                    discountTargetAmount	Double	Required	할인 대상 금액
                    discountAppliedamount	Double	Required	할인 적용 금액
                    discountNo	String	Required	할인 번호
                    productDiscountName	String	Required	상품 할인 명
                    discountRate	Double	Required	할인율
                    discountCondition	Boolean	Required	조건부 할인 여부                     true | false
                    minimumAmount	Double	Required	조건부 할인 여부가 Y일 때 할인 적용을 위해 필요한 최소 사용 금액
                    maximumDiscountCondition	Boolean	Required	최대 할인 여부                     true | false
                    maximumDiscountAmount	Double	Required	최대 할인 여부가 Y일 때 최대 할인 적용 금액
                    validityStartMonth	String	Required	유효 시작 월
                    validityEndMonth	String	Required	유효 종료 월
                    eligibleProductDemandTypeList	List<ProductDemandType>	Required	할인 가능한 상품 청구 유형 목록
                payCurrency	CommonCode	Required	결제 통화
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

        return self.client.get('/discount/getProductDemandCostByDiscountList', params=params)

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
            pageNo	Integer	Optional	페이지 번호
            pageSize	Integer	Optional	페이지 크기             1,000 이하(기본값: 1,000)
            discountNoList.N	List<String>	Optional	조회할 서비스 할인 번호             미 입력 시 전체 할인 이력 응답            할인 번호는 getDiscountList 액션을 통해 확인
            isOrganization	Boolean	Optional	Organization 서비스 계정 통합 조회 여부            마스터만 사용 가능            isOrganization, isPartner 모두 true이면 에러 응답
            isPartner	Boolean	Optional	파트너 계정 조회 여부            파트너 대표만 사용 가능            isOrganization, isPartner 모두 true이면 에러 응답
            memberNoList	List<String>	Optional	회원 번호 목록            마스터 또는 파트너 대표만 사용 가능
            startMonth	String	Optional	조회 시작 월(yyyyMM)            <예시> 202401
            endMonth	String	Optional	조회 마지막 월(yyyyMM)            <예시> 202403            
            responseFormatType	String	Optional	응답 결과의 형식            xml (기본값) | json
        
        Returns:
            Dict: 서비스 요금 할인 현황과 사용 이력 응답 데이터
            private Integer totalRows;
            private List<ProductDiscountHistory> productDiscountHistoryList;
                private String memberNo;
                private ProductDiscount productDiscount;
                private ArrayList<ProductDiscountUseHistory> productDiscountUseHistoryList;
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
        return self.client.get('/discount/getProductDiscountHistoryList', params=params)